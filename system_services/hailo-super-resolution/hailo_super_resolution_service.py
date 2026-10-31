#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import logging
import os
import time
from pathlib import Path
from typing import Any

from aiohttp import web
from PIL import Image, UnidentifiedImageError

from super_resolution import (
    MAX_INPUT_PIXELS,
    SCALE_FACTOR,
    SuperResolutionPipeline,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11442
DEFAULT_MODEL_PATH = "/var/lib/hailo-super-resolution/models/spanf_x4.hef"
MAX_REQUEST_BYTES = 24 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("hailo-super-resolution")


def decode_image_data_uri(value: Any) -> Image.Image:
    if not isinstance(value, str) or "," not in value:
        raise ValueError("image must be a base64-encoded data URI")
    header, encoded = value.split(",", 1)
    if not header.lower().startswith("data:image/") or ";base64" not in header.lower():
        raise ValueError("image must be a base64-encoded image data URI")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(image_bytes)) as source:
            width, height = source.size
            if width < 1 or height < 1:
                raise ValueError("Image contains no pixels")
            if width * height > MAX_INPUT_PIXELS:
                raise ValueError(
                    f"Image has {width * height:,} pixels; the limit is "
                    f"{MAX_INPUT_PIXELS:,} pixels"
                )
            source.load()
            return source.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Could not read uploaded image: {exc}") from exc
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"Could not decode uploaded image: {exc}") from exc


def create_app(model_path: str | Path = DEFAULT_MODEL_PATH) -> web.Application:
    pipeline = SuperResolutionPipeline(model_path)
    inference_lock = asyncio.Lock()
    app = web.Application(client_max_size=MAX_REQUEST_BYTES)

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "model": "spanf_x4",
                "input_shape": [512, 512, 3],
                "scale_factor": SCALE_FACTOR,
                "max_input_pixels": MAX_INPUT_PIXELS,
            }
        )

    async def readiness(_: web.Request) -> web.Response:
        try:
            from device_client import HailoDeviceClient

            async with HailoDeviceClient(timeout=5) as client:
                await client.ping()
        except RuntimeError as exc:
            return web.json_response(
                {"status": "not_ready", "error": str(exc)}, status=503
            )
        return web.json_response({"status": "ready", "device_manager": "connected"})

    async def super_resolve(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            return web.json_response(
                {"error": "Request body must be valid JSON"}, status=400
            )
        if not isinstance(payload, dict):
            return web.json_response(
                {"error": "Request body must be a JSON object"}, status=400
            )
        try:
            image = decode_image_data_uri(payload.get("image"))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        started = time.monotonic()
        try:
            async with inference_lock:
                output, tile_count = await pipeline.upscale(image)
        except (RuntimeError, OSError) as exc:
            logger.exception("SPANF inference failed")
            return web.json_response(
                {"error": f"Super-resolution inference failed: {exc}"}, status=503
            )

        output_buffer = io.BytesIO()
        output.save(output_buffer, format="JPEG", quality=92)
        encoded_output = base64.b64encode(output_buffer.getvalue()).decode("ascii")
        return web.json_response(
            {
                "image": f"data:image/jpeg;base64,{encoded_output}",
                "input_width": image.width,
                "input_height": image.height,
                "output_width": output.width,
                "output_height": output.height,
                "scale_factor": SCALE_FACTOR,
                "tiles_processed": tile_count,
                "inference_time_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )

    app.router.add_get("/health", health)
    app.router.add_get("/health/ready", readiness)
    app.router.add_post("/v1/super-resolve", super_resolve)
    return app


def main() -> None:
    model_path = Path(os.environ.get("HAILO_SUPER_RESOLUTION_HEF", DEFAULT_MODEL_PATH))
    if not model_path.is_file():
        raise FileNotFoundError(f"SPANF HEF not found: {model_path}")
    host = os.environ.get("HAILO_SUPER_RESOLUTION_HOST", DEFAULT_HOST)
    port = int(os.environ.get("HAILO_SUPER_RESOLUTION_PORT", DEFAULT_PORT))
    logger.info("Starting SPANF x4 service on %s:%d", host, port)
    web.run_app(create_app(model_path), host=host, port=port)


if __name__ == "__main__":
    main()
