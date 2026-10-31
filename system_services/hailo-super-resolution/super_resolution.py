from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

INPUT_SIZE = 512
SCALE_FACTOR = 4
OUTPUT_SIZE = INPUT_SIZE * SCALE_FACTOR
TILE_OVERLAP = 64
TILE_STRIDE = INPUT_SIZE - TILE_OVERLAP
MAX_INPUT_PIXELS = 4_000_000
DEVICE_CLIENT_MAX_MESSAGE_BYTES = 24 * 1024 * 1024


def _tile_starts(length: int) -> list[int]:
    if length <= INPUT_SIZE:
        return [0]
    return list(range(0, length, TILE_STRIDE))


def _axis_weights(starts: list[int], index: int, valid_length: int) -> np.ndarray:
    weights = np.full(valid_length * SCALE_FACTOR, 8, dtype=np.uint8)
    if index > 0:
        overlap = max(0, starts[index - 1] + INPUT_SIZE - starts[index])
        overlap_out = min(overlap, valid_length) * SCALE_FACTOR
        if overlap_out:
            ramp = np.rint(np.linspace(1, 8, overlap_out)).astype(np.uint8)
            weights[:overlap_out] = ramp
    if index + 1 < len(starts):
        overlap = max(0, starts[index] + INPUT_SIZE - starts[index + 1])
        overlap_out = min(overlap, valid_length) * SCALE_FACTOR
        if overlap_out:
            ramp = np.rint(np.linspace(1, 8, overlap_out)).astype(np.uint8)
            weights[-overlap_out:] = ramp[::-1]
    return weights


def _extract_tile(image: np.ndarray, top: int, left: int) -> np.ndarray:
    tile = image[top : top + INPUT_SIZE, left : left + INPUT_SIZE]
    pad_height = INPUT_SIZE - tile.shape[0]
    pad_width = INPUT_SIZE - tile.shape[1]
    if pad_height or pad_width:
        mode = "reflect" if tile.shape[0] > 1 and tile.shape[1] > 1 else "edge"
        tile = np.pad(
            tile,
            ((0, pad_height), (0, pad_width), (0, 0)),
            mode=mode,
        )
    return np.ascontiguousarray(tile)


def _encode_tensor(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    return {
        "dtype": str(contiguous.dtype),
        "shape": list(contiguous.shape),
        "data_b64": base64.b64encode(contiguous.tobytes()).decode("ascii"),
    }


def _decode_output(response: dict[str, Any]) -> np.ndarray:
    try:
        outputs = response["result"]["outputs"]
        if not isinstance(outputs, dict) or len(outputs) != 1:
            raise ValueError("SPANF should return exactly one output tensor")
        payload = next(iter(outputs.values()))
        dtype = np.dtype(payload["dtype"])
        shape = tuple(int(size) for size in payload["shape"])
        raw = base64.b64decode(payload["data_b64"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid SPANF output tensor: {exc}") from exc

    if dtype != np.dtype(np.uint8):
        raise RuntimeError(f"SPANF output must be uint8, received {dtype}")
    if shape == (1, OUTPUT_SIZE, OUTPUT_SIZE, 3):
        shape = shape[1:]
    if shape != (OUTPUT_SIZE, OUTPUT_SIZE, 3):
        raise RuntimeError(f"Unexpected SPANF output shape: {shape}")
    expected_bytes = math.prod(shape) * dtype.itemsize
    if len(raw) != expected_bytes:
        raise RuntimeError(
            f"SPANF output byte count mismatch: expected {expected_bytes}, got {len(raw)}"
        )
    return np.frombuffer(raw, dtype=dtype).reshape(shape)


class SuperResolutionPipeline:
    def __init__(
        self,
        model_path: str | Path,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.client_factory = client_factory

    async def upscale(self, image: Image.Image) -> tuple[Image.Image, int]:
        width, height = image.size
        if width < 1 or height < 1:
            raise ValueError("Image contains no pixels")
        if width * height > MAX_INPUT_PIXELS:
            raise ValueError(
                f"Image has {width * height:,} pixels; the limit is "
                f"{MAX_INPUT_PIXELS:,} pixels"
            )

        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        y_starts = _tile_starts(height)
        x_starts = _tile_starts(width)
        output_height = height * SCALE_FACTOR
        output_width = width * SCALE_FACTOR

        # With 1..8 axis weights, at most four overlapping tiles contribute a
        # combined weight of 81, keeping both accumulators safely within uint16.
        pixel_accumulator = np.zeros(
            (output_height, output_width, 3), dtype=np.uint16
        )
        weight_accumulator = np.zeros(
            (output_height, output_width), dtype=np.uint8
        )

        if self.client_factory is None:
            from device_client import HailoDeviceClient

            client_factory = HailoDeviceClient
        else:
            client_factory = self.client_factory
        client = client_factory(
            timeout=120,
            max_message_bytes=DEVICE_CLIENT_MAX_MESSAGE_BYTES,
        )

        tile_count = 0
        try:
            await client.connect()
            for y_index, top in enumerate(y_starts):
                valid_height = min(INPUT_SIZE, height - top)
                y_weights = _axis_weights(y_starts, y_index, valid_height)
                output_top = top * SCALE_FACTOR
                output_bottom = output_top + valid_height * SCALE_FACTOR

                for x_index, left in enumerate(x_starts):
                    valid_width = min(INPUT_SIZE, width - left)
                    x_weights = _axis_weights(x_starts, x_index, valid_width)
                    output_left = left * SCALE_FACTOR
                    output_right = output_left + valid_width * SCALE_FACTOR

                    response = await client.infer(
                        str(self.model_path),
                        {"input": _encode_tensor(_extract_tile(rgb, top, left))},
                        model_type="tensor",
                        model_params={
                            "input_format": "UINT8",
                            "output_format": "UINT8",
                        },
                    )
                    tile_output = _decode_output(response)[
                        : valid_height * SCALE_FACTOR,
                        : valid_width * SCALE_FACTOR,
                    ]
                    tile_weights = y_weights[:, None] * x_weights[None, :]
                    region = (
                        slice(output_top, output_bottom),
                        slice(output_left, output_right),
                    )
                    weighted_pixels = (
                        tile_output.astype(np.uint16) * tile_weights[:, :, None]
                    )
                    pixel_accumulator[region] += weighted_pixels
                    weight_accumulator[region] += tile_weights
                    tile_count += 1

        finally:
            await client.disconnect()

        if np.any(weight_accumulator == 0):
            raise RuntimeError("Tiled inference left uncovered output pixels")
        np.add(
            pixel_accumulator,
            (weight_accumulator[:, :, None] // 2).astype(np.uint16),
            out=pixel_accumulator,
        )
        np.floor_divide(
            pixel_accumulator,
            weight_accumulator[:, :, None],
            out=pixel_accumulator,
        )
        output = pixel_accumulator.astype(np.uint8)
        return Image.fromarray(output), tile_count
