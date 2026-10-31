from __future__ import annotations

import base64
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

STARK_MODEL_NAME = "stark_lightning_repvgg_a0"
STARK_MODEL_INPUTS = {
    f"{STARK_MODEL_NAME}/input_layer1": (128, 128),
    f"{STARK_MODEL_NAME}/input_layer2": (320, 320),
}
STARK_OUTPUT_SUFFIX = "mul_and_add2"
STARK_TEMPLATE_FACTOR = 2.0
STARK_SEARCH_FACTOR = 5.0
STARK_CLIP_MARGIN = 10.0

BYTETRACK_MODEL_NAME = "bytetrack_tiny_mot17"
BYTETRACK_INPUT_SIZE = (608, 1088)
BYTETRACK_OUTPUT_GROUPS = (
    ("conv83", "conv82", "conv81", 32),
    ("conv70", "conv69", "conv68", 16),
    ("conv56", "conv55", "conv54", 8),
)

MAX_VIDEO_FRAMES = 600
MAX_FRAME_PIXELS = 8_000_000
DEFAULT_VIDEO_FPS = 15.0
BYTE_TRACK_SCORE_THRESHOLD = 0.1
BYTE_TRACK_HIGH_SCORE = 0.6
BYTE_TRACK_NEW_TRACK_SCORE = 0.7
BYTE_TRACK_MAX_MISSED_FRAMES = 30


class TrackingError(ValueError):
    pass


class TensorClient(Protocol):
    async def infer(
        self,
        model_path: str,
        input_data: dict[str, Any],
        model_type: str = "tensor",
        model_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class TrackingResult:
    mode: str
    frames_processed: int
    width: int
    height: int
    output_width: int
    output_height: int
    source_fps: float
    inference_time_ms: float
    track_ids: set[int] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "frames_processed": self.frames_processed,
            "width": self.width,
            "height": self.height,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "source_fps": self.source_fps,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "unique_tracks": len(self.track_ids),
        }


def encode_tensor(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    return {
        "dtype": str(contiguous.dtype),
        "shape": list(contiguous.shape),
        "data_b64": base64.b64encode(contiguous.tobytes()).decode("ascii"),
    }


def decode_tensor(payload: dict[str, Any]) -> np.ndarray:
    try:
        dtype = np.dtype(payload["dtype"])
        shape = tuple(int(dimension) for dimension in payload["shape"])
        encoded = payload["data_b64"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Device Manager returned an invalid tensor payload") from exc
    if not shape or any(dimension <= 0 for dimension in shape):
        raise RuntimeError("Device Manager returned an invalid tensor shape")
    try:
        raw = base64.b64decode(encoded, validate=True)
        tensor = np.frombuffer(raw, dtype=dtype)
        return tensor.reshape(shape).copy()
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Device Manager returned malformed tensor data") from exc


def _named_output(outputs: dict[str, Any], suffix: str) -> np.ndarray:
    matches = [
        payload
        for name, payload in outputs.items()
        if name.rsplit("/", 1)[-1] == suffix
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one Device Manager output named {suffix}")
    return decode_tensor(matches[0])


def _unbatch(array: np.ndarray, expected_dimensions: int) -> np.ndarray:
    if array.ndim == expected_dimensions + 1 and array.shape[0] == 1:
        return array[0]
    if array.ndim != expected_dimensions:
        raise RuntimeError(f"Unexpected model output rank: {array.shape}")
    return array


def sample_target(
    image: np.ndarray,
    box: tuple[float, float, float, float] | np.ndarray,
    area_factor: float,
    output_size: int,
) -> tuple[np.ndarray, float, tuple[float, float]]:
    x, y, width, height = (float(value) for value in box)
    crop_size = max(
        int(math.ceil(math.sqrt(max(width, 1e-3) * max(height, 1e-3)) * area_factor)),
        1,
    )
    x1 = int(round(x + width * 0.5 - crop_size * 0.5))
    y1 = int(round(y + height * 0.5 - crop_size * 0.5))
    x2, y2 = x1 + crop_size, y1 + crop_size
    image_height, image_width = image.shape[:2]
    source_x1, source_y1 = max(0, x1), max(0, y1)
    source_x2, source_y2 = min(image_width, x2), min(image_height, y2)
    patch = image[source_y1:source_y2, source_x1:source_x2]
    padding = (
        (source_y1 - y1, y2 - source_y2),
        (source_x1 - x1, x2 - source_x2),
        (0, 0),
    )
    patch = np.pad(patch, padding, mode="constant")
    resized = cv2.resize(
        patch, (output_size, output_size), interpolation=cv2.INTER_LINEAR
    )
    return resized, output_size / crop_size, (float(x1), float(y1))


def clip_box(
    box: np.ndarray, height: int, width: int, margin: float = 0.0
) -> np.ndarray:
    x1, y1, box_width, box_height = (float(value) for value in box)
    x2, y2 = x1 + box_width, y1 + box_height
    effective_margin = min(max(margin, 0.0), float(width), float(height))
    x1 = min(max(0.0, x1), width - effective_margin)
    x2 = min(max(effective_margin, x2), float(width))
    y1 = min(max(0.0, y1), height - effective_margin)
    y2 = min(max(effective_margin, y2), float(height))
    return np.asarray(
        [
            x1,
            y1,
            max(effective_margin, x2 - x1),
            max(effective_margin, y2 - y1),
        ],
        dtype=np.float64,
    )


def map_stark_box(
    normalized_xyxy: np.ndarray,
    previous_box: np.ndarray,
    resize_factor: float,
    crop_origin: tuple[float, float],
    height: int,
    width: int,
) -> np.ndarray:
    if resize_factor <= 0:
        raise TrackingError("STARK search crop has an invalid resize factor")
    x1, y1, x2, y2 = (
        np.asarray(normalized_xyxy, dtype=np.float64).reshape(-1)[:4]
        * (STARK_MODEL_INPUTS[f"{STARK_MODEL_NAME}/input_layer2"][0] / resize_factor)
    )
    mapped = np.asarray(
        [x1 + crop_origin[0], y1 + crop_origin[1], x2 + crop_origin[0], y2 + crop_origin[1]]
    )
    return clip_box(
        np.asarray(
            [mapped[0], mapped[1], mapped[2] - mapped[0], mapped[3] - mapped[1]]
        ),
        height,
        width,
        margin=STARK_CLIP_MARGIN,
    )


def validate_initial_box(
    box: tuple[float, float, float, float] | list[float],
    width: int,
    height: int,
) -> np.ndarray:
    if len(box) != 4:
        raise TrackingError("STARK requires x, y, width, and height for the target box")
    values = np.asarray(box, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise TrackingError("STARK target coordinates must be finite numbers")
    x, y, box_width, box_height = values
    if (
        x < 0
        or y < 0
        or box_width <= 0
        or box_height <= 0
        or x + box_width > width
        or y + box_height > height
    ):
        raise TrackingError(
            f"STARK target box must fit inside the {width}x{height} first frame"
        )
    return values


def letterbox_bytetrack(image_rgb: np.ndarray) -> tuple[np.ndarray, float]:
    target_height, target_width = BYTETRACK_INPUT_SIZE
    image_height, image_width = image_rgb.shape[:2]
    scale = min(target_width / image_width, target_height / image_height)
    resized_width = max(1, int(round(image_width * scale)))
    resized_height = max(1, int(round(image_height * scale)))
    resized = cv2.resize(
        image_rgb, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR
    )
    canvas = np.full(
        (target_height, target_width, 3), 114, dtype=np.uint8
    )
    canvas[:resized_height, :resized_width] = resized
    return canvas, scale


def _nms(
    detections: np.ndarray, iou_threshold: float = 0.65, max_detections: int = 100
) -> np.ndarray:
    if detections.size == 0:
        return np.empty((0, 5), dtype=np.float32)
    order = np.argsort(detections[:, 4])[::-1]
    kept = []
    while order.size and len(kept) < max_detections:
        selected = int(order[0])
        kept.append(selected)
        remaining = order[1:]
        if remaining.size == 0:
            break
        selected_box = detections[selected, :4]
        other_boxes = detections[remaining, :4]
        intersection_left_top = np.maximum(selected_box[:2], other_boxes[:, :2])
        intersection_right_bottom = np.minimum(selected_box[2:], other_boxes[:, 2:])
        intersection_size = np.maximum(
            intersection_right_bottom - intersection_left_top, 0.0
        )
        intersection = intersection_size[:, 0] * intersection_size[:, 1]
        selected_area = np.prod(np.maximum(selected_box[2:] - selected_box[:2], 0.0))
        other_area = np.prod(
            np.maximum(other_boxes[:, 2:] - other_boxes[:, :2], 0.0), axis=1
        )
        union = selected_area + other_area - intersection
        iou = np.divide(
            intersection,
            union,
            out=np.zeros_like(intersection),
            where=union > 0,
        )
        order = remaining[iou <= iou_threshold]
    return detections[np.asarray(kept, dtype=np.int64)]


def decode_bytetrack_detections(
    outputs: dict[str, Any],
    scale: float,
    original_width: int,
    original_height: int,
    score_threshold: float = BYTE_TRACK_SCORE_THRESHOLD,
) -> np.ndarray:
    model_height, model_width = BYTETRACK_INPUT_SIZE
    decoded = []
    for box_name, objectness_name, class_name, stride in BYTETRACK_OUTPUT_GROUPS:
        raw_boxes = _unbatch(_named_output(outputs, box_name), 3).astype(np.float32)
        objectness = _unbatch(_named_output(outputs, objectness_name), 3).astype(
            np.float32
        )
        class_scores = _unbatch(_named_output(outputs, class_name), 3).astype(
            np.float32
        )
        if (
            raw_boxes.shape[-1] != 4
            or objectness.shape[-1] != 1
            or class_scores.shape[-1] != 1
        ):
            raise RuntimeError(f"Unexpected ByteTrack output shapes for stride {stride}")
        if (
            raw_boxes.shape[:2] != objectness.shape[:2]
            or raw_boxes.shape[:2] != class_scores.shape[:2]
        ):
            raise RuntimeError(f"ByteTrack outputs do not align for stride {stride}")

        grid_y, grid_x = np.meshgrid(
            np.arange(raw_boxes.shape[0], dtype=np.float32),
            np.arange(raw_boxes.shape[1], dtype=np.float32),
            indexing="ij",
        )
        centers_x = (raw_boxes[..., 0] + grid_x) * stride
        centers_y = (raw_boxes[..., 1] + grid_y) * stride
        widths = np.exp(np.clip(raw_boxes[..., 2], -10.0, 10.0)) * stride
        heights = np.exp(np.clip(raw_boxes[..., 3], -10.0, 10.0)) * stride
        scores = objectness[..., 0] * class_scores[..., 0]
        valid = scores >= score_threshold
        if not np.any(valid):
            continue

        boxes = np.stack(
            (
                centers_x - widths * 0.5,
                centers_y - heights * 0.5,
                centers_x + widths * 0.5,
                centers_y + heights * 0.5,
            ),
            axis=-1,
        )[valid]
        boxes[:, (0, 2)] = np.clip(boxes[:, (0, 2)] / scale, 0, original_width)
        boxes[:, (1, 3)] = np.clip(boxes[:, (1, 3)] / scale, 0, original_height)
        decoded.append(np.column_stack((boxes, scores[valid])))

    if not decoded:
        return np.empty((0, 5), dtype=np.float32)
    return _nms(np.concatenate(decoded).astype(np.float32))


def _intersection_over_union(first: np.ndarray, second: np.ndarray) -> float:
    left_top = np.maximum(first[:2], second[:2])
    right_bottom = np.minimum(first[2:], second[2:])
    intersection_size = np.maximum(right_bottom - left_top, 0.0)
    intersection = float(intersection_size[0] * intersection_size[1])
    first_area = float(np.prod(np.maximum(first[2:] - first[:2], 0.0)))
    second_area = float(np.prod(np.maximum(second[2:] - second[:2], 0.0)))
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    box: np.ndarray
    score: float
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    missed_frames: int = 0

    def predicted_box(self) -> np.ndarray:
        return self.box + self.velocity * (self.missed_frames + 1)


class ByteTrackAssociator:
    def __init__(
        self,
        high_score: float = BYTE_TRACK_HIGH_SCORE,
        new_track_score: float = BYTE_TRACK_NEW_TRACK_SCORE,
        max_missed_frames: int = BYTE_TRACK_MAX_MISSED_FRAMES,
    ) -> None:
        self.high_score = high_score
        self.new_track_score = new_track_score
        self.max_missed_frames = max_missed_frames
        self._tracks: dict[int, _Track] = {}
        self._next_track_id = 1

    def update(self, detections: np.ndarray) -> list[_Track]:
        detections = np.asarray(detections, dtype=np.float32).reshape(-1, 5)
        active_tracks = list(self._tracks.values())
        high_indices = [
            index
            for index, detection in enumerate(detections)
            if detection[4] >= self.high_score
        ]
        low_indices = [
            index
            for index, detection in enumerate(detections)
            if BYTE_TRACK_SCORE_THRESHOLD <= detection[4] < self.high_score
        ]
        unmatched_tracks = {track.track_id for track in active_tracks}
        unmatched_high = set(high_indices)

        high_matches = self._match(
            active_tracks,
            detections,
            high_indices,
            use_detection_score=True,
            minimum_affinity=0.1,
        )
        for track, detection_index in high_matches:
            self._update_track(track, detections[detection_index])
            unmatched_tracks.discard(track.track_id)
            unmatched_high.discard(detection_index)

        low_matches = self._match(
            [self._tracks[track_id] for track_id in unmatched_tracks],
            detections,
            low_indices,
            use_detection_score=False,
            minimum_affinity=0.5,
        )
        for track, detection_index in low_matches:
            self._update_track(track, detections[detection_index])
            unmatched_tracks.discard(track.track_id)

        for track_id in unmatched_tracks:
            self._tracks[track_id].missed_frames += 1

        for detection_index in unmatched_high:
            detection = detections[detection_index]
            if detection[4] >= self.new_track_score:
                track_id = self._next_track_id
                self._next_track_id += 1
                self._tracks[track_id] = _Track(
                    track_id=track_id,
                    box=detection[:4].copy(),
                    score=float(detection[4]),
                )

        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if track.missed_frames > self.max_missed_frames
        ]
        for track_id in expired:
            del self._tracks[track_id]
        return [
            track
            for track in self._tracks.values()
            if track.missed_frames == 0
        ]

    @staticmethod
    def _match(
        tracks: list[_Track],
        detections: np.ndarray,
        detection_indices: list[int],
        use_detection_score: bool,
        minimum_affinity: float,
    ) -> list[tuple[_Track, int]]:
        candidates = []
        for track in tracks:
            predicted = track.predicted_box()
            for detection_index in detection_indices:
                detection = detections[detection_index]
                overlap = _intersection_over_union(predicted, detection[:4])
                affinity = overlap * float(detection[4]) if use_detection_score else overlap
                if affinity >= minimum_affinity:
                    candidates.append((affinity, track.track_id, detection_index))
        candidates.sort(reverse=True)

        tracks_by_id = {track.track_id: track for track in tracks}
        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        matches = []
        for _, track_id, detection_index in candidates:
            if track_id in used_tracks or detection_index in used_detections:
                continue
            used_tracks.add(track_id)
            used_detections.add(detection_index)
            matches.append((tracks_by_id[track_id], detection_index))
        return matches

    @staticmethod
    def _update_track(track: _Track, detection: np.ndarray) -> None:
        new_box = detection[:4].copy()
        track.velocity = 0.5 * track.velocity + 0.5 * (new_box - track.box)
        track.box = new_box
        track.score = float(detection[4])
        track.missed_frames = 0


class TrackingPipeline:
    def __init__(
        self,
        client: TensorClient,
        stark_model_path: str | Path,
        bytetrack_model_path: str | Path,
    ) -> None:
        self.client = client
        self.stark_model_path = str(stark_model_path)
        self.bytetrack_model_path = str(bytetrack_model_path)

    async def process_capture(
        self,
        capture: Any,
        output_path: str | Path,
        mode: str,
        initial_box: tuple[float, float, float, float] | list[float] | None = None,
        duration_seconds: float | None = None,
    ) -> TrackingResult:
        if mode not in {"stark", "bytetrack"}:
            raise TrackingError("mode must be 'stark' or 'bytetrack'")
        if mode == "stark" and initial_box is None:
            raise TrackingError("STARK requires an initial target box")
        if mode == "bytetrack" and initial_box is not None:
            raise TrackingError("An initial target box only applies to STARK mode")
        if duration_seconds is not None and not 1 <= duration_seconds <= 20:
            raise TrackingError("Camera duration must be between 1 and 20 seconds")
        if not capture.isOpened():
            raise TrackingError("Could not open video or camera source")

        started = time.monotonic()
        writer = None
        try:
            ok, frame = capture.read()
            if not ok or frame is None:
                raise TrackingError("Video or camera source returned no frames")
            height, width = frame.shape[:2]
            if width * height > MAX_FRAME_PIXELS:
                raise TrackingError(
                    f"Frames may not exceed {MAX_FRAME_PIXELS:,} pixels"
                )
            target_box = (
                validate_initial_box(initial_box, width, height)
                if initial_box is not None
                else None
            )
            source_fps = self._source_fps(capture)
            output_width = width + (width % 2)
            output_height = height + (height % 2)
            output_path = Path(output_path)
            writer = cv2.VideoWriter(
                str(output_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                source_fps,
                (output_width, output_height),
            )
            if not writer.isOpened():
                raise TrackingError("OpenCV could not create the output MP4")

            if mode == "stark":
                template, _, _ = sample_target(
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    target_box,
                    STARK_TEMPLATE_FACTOR,
                    STARK_MODEL_INPUTS[f"{STARK_MODEL_NAME}/input_layer1"][0],
                )
                state = target_box.copy()
                tracks = {1}
                inference_time_ms = 0.0
                frame_count = 0
                while True:
                    current_height, current_width = frame.shape[:2]
                    if (current_width, current_height) != (width, height):
                        raise TrackingError("Video dimensions changed between frames")
                    if frame_count >= MAX_VIDEO_FRAMES:
                        raise TrackingError(
                            f"Video exceeds the {MAX_VIDEO_FRAMES}-frame limit"
                        )
                    if frame_count > 0:
                        state, elapsed = await self._stark_step(
                            frame, template, state
                        )
                        inference_time_ms += elapsed
                    self._draw_box(frame, state, "Target", (40, 220, 40))
                    self._write_frame(writer, frame, output_width, output_height)
                    frame_count += 1
                    if (
                        duration_seconds is not None
                        and time.monotonic() - started >= duration_seconds
                    ):
                        break
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        if duration_seconds is not None:
                            raise TrackingError(
                                "Camera stopped before the requested capture duration"
                            )
                        break
                track_ids = tracks
            else:
                associator = ByteTrackAssociator()
                track_ids = set()
                inference_time_ms = 0.0
                frame_count = 0
                while True:
                    current_height, current_width = frame.shape[:2]
                    if (current_width, current_height) != (width, height):
                        raise TrackingError("Video dimensions changed between frames")
                    if frame_count >= MAX_VIDEO_FRAMES:
                        raise TrackingError(
                            f"Video exceeds the {MAX_VIDEO_FRAMES}-frame limit"
                        )
                    detections, elapsed = await self._bytetrack_step(frame)
                    inference_time_ms += elapsed
                    active_tracks = associator.update(detections)
                    for track in active_tracks:
                        track_ids.add(track.track_id)
                        self._draw_box(
                            frame,
                            track.box,
                            f"Person {track.track_id}",
                            self._track_color(track.track_id),
                        )
                    self._write_frame(writer, frame, output_width, output_height)
                    frame_count += 1
                    if (
                        duration_seconds is not None
                        and time.monotonic() - started >= duration_seconds
                    ):
                        break
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        if duration_seconds is not None:
                            raise TrackingError(
                                "Camera stopped before the requested capture duration"
                            )
                        break

            if frame_count == 0:
                raise TrackingError("No frames were processed")
            return TrackingResult(
                mode=mode,
                frames_processed=frame_count,
                width=width,
                height=height,
                output_width=output_width,
                output_height=output_height,
                source_fps=source_fps,
                inference_time_ms=inference_time_ms,
                track_ids=track_ids,
            )
        finally:
            capture.release()
            if writer is not None:
                writer.release()

    async def _stark_step(
        self, frame_bgr: np.ndarray, template: np.ndarray, state: np.ndarray
    ) -> tuple[np.ndarray, float]:
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        search, resize_factor, origin = sample_target(
            frame_rgb, state, STARK_SEARCH_FACTOR, 320
        )
        inputs = {
            f"{STARK_MODEL_NAME}/input_layer1": encode_tensor(template),
            f"{STARK_MODEL_NAME}/input_layer2": encode_tensor(search),
        }
        outputs, elapsed = await self._infer(
            self.stark_model_path, {"inputs": inputs}
        )
        normalized_box = _named_output(outputs, STARK_OUTPUT_SUFFIX)
        next_box = map_stark_box(
            normalized_box,
            state,
            resize_factor,
            origin,
            frame_bgr.shape[0],
            frame_bgr.shape[1],
        )
        return next_box, elapsed

    async def _bytetrack_step(
        self, frame_bgr: np.ndarray
    ) -> tuple[np.ndarray, float]:
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        model_frame, scale = letterbox_bytetrack(frame_rgb)
        outputs, elapsed = await self._infer(
            self.bytetrack_model_path,
            {"input": encode_tensor(model_frame)},
        )
        detections = decode_bytetrack_detections(
            outputs,
            scale,
            frame_bgr.shape[1],
            frame_bgr.shape[0],
        )
        return detections, elapsed

    async def _infer(
        self, model_path: str, input_data: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        response = await self.client.infer(
            model_path,
            input_data,
            model_type="tensor",
            model_params={"input_format": "UINT8", "output_format": "FLOAT32"},
        )
        result = response.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("outputs"), dict):
            raise RuntimeError("Device Manager response did not contain tensor outputs")
        elapsed = float(
            response.get("inference_time_ms", (time.perf_counter() - started) * 1000)
        )
        return result["outputs"], elapsed

    @staticmethod
    def _source_fps(capture: Any) -> float:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps < 1.0 or fps > 60.0:
            return DEFAULT_VIDEO_FPS
        return fps

    @staticmethod
    def _write_frame(
        writer: cv2.VideoWriter,
        frame: np.ndarray,
        output_width: int,
        output_height: int,
    ) -> None:
        if frame.shape[1] != output_width or frame.shape[0] != output_height:
            frame = cv2.copyMakeBorder(
                frame,
                0,
                output_height - frame.shape[0],
                0,
                output_width - frame.shape[1],
                cv2.BORDER_CONSTANT,
                value=(0, 0, 0),
            )
        writer.write(frame)

    @staticmethod
    def _draw_box(
        frame: np.ndarray,
        box: np.ndarray,
        label: str,
        color: tuple[int, int, int],
    ) -> None:
        x, y, width, height = (int(round(value)) for value in box)
        cv2.rectangle(frame, (x, y), (x + width, y + height), color, 2)
        cv2.putText(
            frame,
            label,
            (x, max(16, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    @staticmethod
    def _track_color(track_id: int) -> tuple[int, int, int]:
        return (
            64 + (track_id * 37) % 192,
            64 + (track_id * 67) % 192,
            64 + (track_id * 97) % 192,
        )
