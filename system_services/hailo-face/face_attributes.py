"""SCRFD detection and MiVOLO face-only age/gender estimation."""

from __future__ import annotations

import asyncio
import base64
import io
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

SCRFD_HEIGHT = 384
SCRFD_WIDTH = 640
MIVOLO_SIZE = 224
SCRFD_STRIDES = (8, 16, 32)
# Per-side expansion of the returned face crop, as a percent of box width/height
CROP_PADDING_PERCENT = 15


def _decode_tensor(payload: dict[str, Any]) -> np.ndarray:
    raw = base64.b64decode(payload["data_b64"], validate=True)
    return np.frombuffer(raw, dtype=np.dtype(payload["dtype"])).reshape(
        payload["shape"]
    )


def _encode_tensor(array: np.ndarray) -> dict[str, Any]:
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -80.0, 80.0)
    return 1.0 / (1.0 + np.exp(-values))


def _nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    order = np.argsort(scores)[::-1]
    kept = []
    while order.size:
        current = int(order[0])
        kept.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        left = np.maximum(boxes[current, 0], boxes[rest, 0])
        top = np.maximum(boxes[current, 1], boxes[rest, 1])
        right = np.minimum(boxes[current, 2], boxes[rest, 2])
        bottom = np.minimum(boxes[current, 3], boxes[rest, 3])
        intersection = np.maximum(0.0, right - left) * np.maximum(0.0, bottom - top)
        area_current = max(0.0, boxes[current, 2] - boxes[current, 0]) * max(
            0.0, boxes[current, 3] - boxes[current, 1]
        )
        area_rest = np.maximum(0.0, boxes[rest, 2] - boxes[rest, 0]) * np.maximum(
            0.0, boxes[rest, 3] - boxes[rest, 1]
        )
        union = area_current + area_rest - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        order = rest[iou <= threshold]
    return kept


def _scrfd_resize_geometry(
    original_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    original_width, original_height = original_size
    scale = min(SCRFD_WIDTH / original_width, SCRFD_HEIGHT / original_height)
    resized_width = min(SCRFD_WIDTH, max(1, round(original_width * scale)))
    resized_height = min(SCRFD_HEIGHT, max(1, round(original_height * scale)))
    pad_left = (SCRFD_WIDTH - resized_width) // 2
    pad_top = (SCRFD_HEIGHT - resized_height) // 2
    return resized_width, resized_height, pad_left, pad_top


def prepare_scrfd_input(image: np.ndarray) -> np.ndarray:
    original_height, original_width = image.shape[:2]
    resized_width, resized_height, pad_left, pad_top = _scrfd_resize_geometry(
        (original_width, original_height)
    )
    resized = np.asarray(
        Image.fromarray(image).resize(
            (resized_width, resized_height), Image.Resampling.BILINEAR
        ),
        dtype=np.uint8,
    )
    framed = np.zeros((SCRFD_HEIGHT, SCRFD_WIDTH, 3), dtype=np.uint8)
    framed[
        pad_top:pad_top + resized_height,
        pad_left:pad_left + resized_width,
    ] = resized
    return framed


def postprocess_scrfd(
    outputs: dict[str, Any],
    original_size: tuple[int, int],
    score_threshold: float = 0.5,
    nms_threshold: float = 0.4,
    max_faces: int = 10,
) -> list[dict[str, Any]]:
    grouped: dict[int, dict[tuple[int, int], np.ndarray]] = {8: {}, 2: {}, 20: {}}
    for payload in outputs.values():
        tensor = _decode_tensor(payload)
        if tensor.ndim == 4 and tensor.shape[0] == 1:
            tensor = tensor[0]
        if tensor.ndim == 3 and tensor.shape[-1] in grouped:
            grouped[tensor.shape[-1]][tensor.shape[:2]] = tensor.astype(np.float32)

    if any(len(grouped[channels]) != 3 for channels in grouped):
        raise ValueError("SCRFD outputs must contain box, score, and landmark tensors at 3 scales")

    input_boxes = []
    input_scores = []
    input_landmarks = []
    for height, width in sorted(grouped[2], reverse=True):
        boxes = grouped[8].get((height, width))
        landmarks = grouped[20].get((height, width))
        scores = grouped[2][(height, width)]
        if boxes is None or landmarks is None:
            raise ValueError("SCRFD output scales do not align")
        stride_y = SCRFD_HEIGHT / height
        stride_x = SCRFD_WIDTH / width
        if stride_x != stride_y:
            raise ValueError("SCRFD output scale has inconsistent strides")
        stride = stride_x

        scores = scores.reshape(-1)
        if scores.size and (scores.min() < 0.0 or scores.max() > 1.0):
            scores = _sigmoid(scores)
        box_offsets = boxes.reshape(-1, 4)
        landmark_offsets = landmarks.reshape(-1, 10)

        grid_y, grid_x = np.mgrid[:height, :width]
        centers = np.stack((grid_x, grid_y), axis=-1).reshape(-1, 2)
        centers = np.repeat(centers, 2, axis=0).astype(np.float32) * stride
        input_boxes.append(
            np.column_stack(
                (
                    centers[:, 0] - box_offsets[:, 0] * stride,
                    centers[:, 1] - box_offsets[:, 1] * stride,
                    centers[:, 0] + box_offsets[:, 2] * stride,
                    centers[:, 1] + box_offsets[:, 3] * stride,
                )
            )
        )
        input_scores.append(scores)
        points = landmark_offsets.reshape(-1, 5, 2)
        points[..., 0] = centers[:, None, 0] + points[..., 0] * stride
        points[..., 1] = centers[:, None, 1] + points[..., 1] * stride
        input_landmarks.append(points)

    boxes = np.concatenate(input_boxes)
    scores = np.concatenate(input_scores)
    landmarks = np.concatenate(input_landmarks)
    candidates = np.flatnonzero(scores >= score_threshold)
    if not candidates.size:
        return []

    boxes = boxes[candidates]
    scores = scores[candidates]
    landmarks = landmarks[candidates]
    kept = _nms(boxes, scores, nms_threshold)[:max_faces]
    original_width, original_height = original_size
    resized_width, resized_height, pad_left, pad_top = _scrfd_resize_geometry(
        original_size
    )
    scale_x = resized_width / original_width
    scale_y = resized_height / original_height
    results = []
    for index in kept:
        x1, y1, x2, y2 = boxes[index]
        x1, x2 = np.clip(
            (x1 - pad_left, x2 - pad_left), 0, resized_width
        ) / scale_x
        y1, y2 = np.clip(
            (y1 - pad_top, y2 - pad_top), 0, resized_height
        ) / scale_y
        points = landmarks[index].copy()
        points[:, 0] = np.clip(
            points[:, 0] - pad_left, 0, resized_width
        ) / scale_x
        points[:, 1] = np.clip(
            points[:, 1] - pad_top, 0, resized_height
        ) / scale_y
        results.append(
            {
                "bbox": [
                    int(round(x1)),
                    int(round(y1)),
                    int(round(max(0.0, x2 - x1))),
                    int(round(max(0.0, y2 - y1))),
                ],
                "confidence": float(scores[index]),
                "landmarks": np.rint(points).astype(int).tolist(),
            }
        )
    return results


def prepare_mivolo_face_input(
    image: np.ndarray, bbox: list[int]
) -> tuple[np.ndarray, np.ndarray]:
    x, y, width, height = bbox
    x1, y1 = max(0, x), max(0, y)
    x2 = min(image.shape[1], x + width)
    y2 = min(image.shape[0], y + height)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError("SCRFD returned an empty face crop")

    scale = min(MIVOLO_SIZE / crop.shape[1], MIVOLO_SIZE / crop.shape[0])
    resized = np.asarray(
        Image.fromarray(crop).resize(
            (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
            Image.Resampling.BILINEAR,
        ),
        dtype=np.uint8,
    )
    face = np.zeros((MIVOLO_SIZE, MIVOLO_SIZE, 3), dtype=np.uint8)
    top = (MIVOLO_SIZE - resized.shape[0]) // 2
    left = (MIVOLO_SIZE - resized.shape[1]) // 2
    face[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
    tensor = np.zeros((MIVOLO_SIZE, MIVOLO_SIZE, 6), dtype=np.float32)
    tensor[:, :, :3] = face
    return tensor, crop


def decode_mivolo_output(outputs: dict[str, Any]) -> dict[str, Any]:
    if not outputs:
        raise ValueError("MiVOLO returned no output tensors")
    values = _decode_tensor(next(iter(outputs.values()))).reshape(-1)
    if values.size != 3:
        raise ValueError(f"MiVOLO returned {values.size} values, expected 3")
    gender_logits = values[:2].astype(np.float64)
    shifted = gender_logits - np.max(gender_logits)
    exp_scores = np.exp(shifted)
    gender_scores = exp_scores / exp_scores.sum()
    male_score, female_score = (float(score) for score in gender_scores)
    return {
        "age_years": round(float(values[2]), 1),
        "gender": "male" if male_score >= female_score else "female",
        "gender_scores": {"male": male_score, "female": female_score},
    }


def _crop_data_uri(crop: np.ndarray) -> str:
    buffer = io.BytesIO()
    Image.fromarray(crop).save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _padded_face_crop(image: np.ndarray, bbox: list[int]) -> np.ndarray:
    x, y, width, height = bbox
    pad_x = (width * CROP_PADDING_PERCENT + 99) // 100
    pad_y = (height * CROP_PADDING_PERCENT + 99) // 100
    x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
    x2 = min(image.shape[1], x + width + pad_x)
    y2 = min(image.shape[0], y + height + pad_y)
    return image[y1:y2, x1:x2]


class FaceAttributePipeline:
    def __init__(
        self,
        scrfd_hef: str,
        mivolo_hef: str,
        score_threshold: float = 0.5,
        nms_threshold: float = 0.4,
        max_faces: int = 10,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.scrfd_hef = Path(scrfd_hef)
        self.mivolo_hef = Path(mivolo_hef)
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.max_faces = max_faces
        self.client_factory = client_factory

    def analyze(self, image: Image.Image) -> dict[str, Any]:
        if not self.scrfd_hef.is_file() or not self.mivolo_hef.is_file():
            raise FileNotFoundError("SCRFD and MiVOLO Hailo-10H HEFs must be installed")
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if rgb.size == 0:
            raise ValueError("Image contains no pixels")
        return asyncio.run(self._analyze(rgb))

    async def _analyze(self, image: np.ndarray) -> dict[str, Any]:
        if self.client_factory is None:
            from device_client import HailoDeviceClient

            client_factory = HailoDeviceClient
        else:
            client_factory = self.client_factory
        client = client_factory(timeout=60)
        await client.connect()
        started = time.monotonic()
        try:
            resized = prepare_scrfd_input(image)
            detection = await client.infer(
                str(self.scrfd_hef),
                {"input": _encode_tensor(resized)},
                model_type="tensor",
                model_params={"input_format": "UINT8", "output_format": "FLOAT32"},
            )
            faces = postprocess_scrfd(
                detection["result"]["outputs"],
                original_size=(image.shape[1], image.shape[0]),
                score_threshold=self.score_threshold,
                nms_threshold=self.nms_threshold,
                max_faces=self.max_faces,
            )

            for face in faces:
                tensor, _ = prepare_mivolo_face_input(image, face["bbox"])
                response = await client.infer(
                    str(self.mivolo_hef),
                    {"input": _encode_tensor(tensor)},
                    model_type="tensor",
                    model_params={"input_format": "FLOAT32", "output_format": "FLOAT32"},
                )
                face.update(decode_mivolo_output(response["result"]["outputs"]))
                face["crop"] = _crop_data_uri(_padded_face_crop(image, face["bbox"]))
            return {
                "model": "scrfd_2.5g_384_640+mivolo_d1",
                "count": len(faces),
                "faces": faces,
                "inference_time_ms": round((time.monotonic() - started) * 1000, 2),
            }
        finally:
            await client.disconnect()
