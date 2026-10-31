#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
from aiohttp import web

from device_client import HailoDeviceClient
from tracking_pipeline import (
    MAX_FRAME_PIXELS,
    MAX_VIDEO_FRAMES,
    TrackingError,
    TrackingPipeline,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11443
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 80 * 1024 * 1024
MAX_CAMERA_DURATION = 20
CAMERA_FPS = 15
USB_CAMERA_WIDTH = int(os.environ.get("HAILO_TRACKING_USB_WIDTH", "640"))
USB_CAMERA_HEIGHT = int(os.environ.get("HAILO_TRACKING_USB_HEIGHT", "480"))
USB_CAMERA_DEVICE = os.environ.get("HAILO_TRACKING_USB_DEVICE", "/dev/video0")
CSI_CAMERA_WIDTH = int(os.environ.get("HAILO_TRACKING_CSI_WIDTH", "1280"))
CSI_CAMERA_HEIGHT = int(os.environ.get("HAILO_TRACKING_CSI_HEIGHT", "720"))
CSI_CAMERA_INDEX = int(os.environ.get("HAILO_TRACKING_CSI_INDEX", "0"))
STARK_MODEL_PATH = os.environ.get(
    "HAILO_TRACKING_STARK_HEF",
    "/var/lib/hailo-tracking/models/stark_lightning_repvgg_a0.hef",
)
BYTETRACK_MODEL_PATH = os.environ.get(
    "HAILO_TRACKING_BYTETRACK_HEF",
    "/var/lib/hailo-tracking/models/bytetrack_tiny_mot17.hef",
)

logger = logging.getLogger("hailo-tracking")


class CameraError(RuntimeError):
    pass


class TrackingService:
    def __init__(self) -> None:
        self.client = HailoDeviceClient(timeout=60)
        self.pipeline = TrackingPipeline(
            self.client, STARK_MODEL_PATH, BYTETRACK_MODEL_PATH
        )
        self.process_lock = asyncio.Lock()
        self.camera_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.disconnect()


SERVICE_KEY = web.AppKey("tracking_service", TrackingService)


async def health(_: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "service": "hailo-tracking",
            "models_load_on_demand": True,
        }
    )


async def readiness(request: web.Request) -> web.Response:
    service = request.app[SERVICE_KEY]
    missing = [
        path
        for path in (STARK_MODEL_PATH, BYTETRACK_MODEL_PATH)
        if not Path(path).is_file()
    ]
    if missing:
        return web.json_response(
            {"status": "not_ready", "missing_models": missing}, status=503
        )
    try:
        await service.client.ping()
    except RuntimeError as exc:
        logger.warning("Device Manager readiness check failed: %s", exc)
        return web.json_response(
            {"status": "not_ready", "device_manager_error": str(exc)}, status=503
        )
    return web.json_response(
        {
            "status": "ready",
            "models": ["stark_lightning_repvgg_a0", "bytetrack_tiny_mot17"],
            "model_loading": "on demand",
        }
    )


async def info(_: web.Request) -> web.Response:
    return web.json_response(
        {
            "service": "hailo-tracking",
            "trackers": {
                "stark": {
                    "model": "stark_lightning_repvgg_a0",
                    "input": "single target box on the first frame",
                    "input_shape": [320, 320, 3],
                    "template_shape": [128, 128, 3],
                },
                "bytetrack": {
                    "model": "bytetrack_tiny_mot17",
                    "input": "automatic pedestrian detection and IDs",
                    "input_shape": [608, 1088, 3],
                },
            },
            "sources": {
                "video_upload": True,
                "usb_camera_device": USB_CAMERA_DEVICE,
                "csi_camera_backend": "rpicam-vid",
            },
            "limits": {
                "max_video_upload_bytes": MAX_UPLOAD_BYTES,
                "max_video_frames": MAX_VIDEO_FRAMES,
                "max_camera_duration_seconds": MAX_CAMERA_DURATION,
                "max_camera_capture_bytes": MAX_UPLOAD_BYTES,
            },
        }
    )


async def preview_video(request: web.Request) -> web.Response:
    with tempfile.TemporaryDirectory(prefix="hailo-tracking-") as temp_dir:
        video_path = Path(temp_dir) / "input-video"
        await _save_video_upload(request, video_path)
        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                raise web.HTTPBadRequest(text="Uploaded file is not a readable video")
            ok, frame = capture.read()
            if not ok or frame is None:
                raise web.HTTPBadRequest(text="Uploaded video contains no frames")
        finally:
            capture.release()
        return _jpeg_response(frame)


async def preview_camera(request: web.Request) -> web.Response:
    source = request.query.get("source", "usb").lower()
    service = request.app[SERVICE_KEY]
    async with service.camera_lock:
        try:
            if source == "usb":
                frame = await asyncio.to_thread(_read_usb_preview)
            elif source == "csi":
                frame = await asyncio.to_thread(_read_csi_preview)
            else:
                raise web.HTTPBadRequest(text="source must be 'usb' or 'csi'")
        except CameraError as exc:
            logger.warning("Camera preview failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=503)
    return _jpeg_response(frame)


async def track_video(request: web.Request) -> web.Response:
    service = request.app[SERVICE_KEY]
    with tempfile.TemporaryDirectory(prefix="hailo-tracking-") as temp_dir:
        video_path = Path(temp_dir) / "input-video"
        output_path = Path(temp_dir) / "tracked.mp4"
        fields = await _save_video_upload(request, video_path)
        mode, initial_box = _parse_tracking_request(fields)
        capture = cv2.VideoCapture(str(video_path))
        try:
            async with service.process_lock:
                result = await service.pipeline.process_capture(
                    capture, output_path, mode, initial_box
                )
        except TrackingError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            logger.exception("Device Manager tracking inference failed")
            return web.json_response({"error": str(exc)}, status=503)
        return _video_response(output_path, result)


async def track_camera(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise web.HTTPBadRequest(text="Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text="Request body must be a JSON object")
    mode, initial_box = _parse_tracking_request(payload)
    source = str(payload.get("source", "usb")).lower()
    duration = _parse_camera_duration(payload.get("duration_seconds", 5))
    if source not in {"usb", "csi"}:
        raise web.HTTPBadRequest(text="source must be 'usb' or 'csi'")

    service = request.app[SERVICE_KEY]
    with tempfile.TemporaryDirectory(prefix="hailo-tracking-") as temp_dir:
        output_path = Path(temp_dir) / "tracked.mp4"
        try:
            async with service.process_lock:
                async with service.camera_lock:
                    if source == "usb":
                        input_path = Path(temp_dir) / "camera.mp4"
                        await asyncio.to_thread(
                            _capture_usb_clip, input_path, duration
                        )
                    else:
                        input_path = Path(temp_dir) / "camera.mp4"
                        await asyncio.to_thread(
                            _capture_csi_clip, input_path, duration
                        )
                capture = cv2.VideoCapture(str(input_path))
                result = await service.pipeline.process_capture(
                    capture, output_path, mode, initial_box
                )
        except web.HTTPException:
            raise
        except CameraError as exc:
            logger.warning("Camera capture failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=503)
        except TrackingError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            logger.exception("Device Manager tracking inference failed")
            return web.json_response({"error": str(exc)}, status=503)
        return _video_response(output_path, result)


def _parse_camera_duration(value: Any) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(
            text="duration_seconds must be a number between 1 and 20"
        ) from exc
    if not math.isfinite(duration) or not 1 <= duration <= MAX_CAMERA_DURATION:
        raise web.HTTPBadRequest(
            text="duration_seconds must be between 1 and 20"
        )
    return duration


def _parse_tracking_request(
    fields: dict[str, Any],
) -> tuple[str, tuple[float, float, float, float] | None]:
    mode = str(fields.get("mode", "")).lower()
    if mode not in {"stark", "bytetrack"}:
        raise web.HTTPBadRequest(text="mode must be 'stark' or 'bytetrack'")
    if mode == "bytetrack":
        if any(fields.get(name) not in (None, "") for name in ("x", "y", "width", "height")):
            raise web.HTTPBadRequest(
                text="Initial target coordinates only apply to STARK mode"
            )
        return mode, None

    try:
        box = tuple(float(fields[name]) for name in ("x", "y", "width", "height"))
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(
            text="STARK requires numeric x, y, width, and height coordinates"
        ) from exc
    if not all(math.isfinite(value) for value in box):
        raise web.HTTPBadRequest(text="STARK target coordinates must be finite")
    return mode, box


async def _save_video_upload(
    request: web.Request, video_path: Path
) -> dict[str, str]:
    if request.content_length is not None and request.content_length > MAX_UPLOAD_BYTES + 1024 * 1024:
        raise web.HTTPRequestEntityTooLarge(
            max_size=MAX_UPLOAD_BYTES + 1024 * 1024,
            actual_size=request.content_length,
        )
    reader = await request.multipart()
    fields: dict[str, str] = {}
    found_video = False
    while True:
        field = await reader.next()
        if field is None:
            break
        if field.name == "video":
            if found_video:
                raise web.HTTPBadRequest(text="Only one 'video' upload is allowed")
            found_video = True
            actual_size = 0
            with video_path.open("wb") as target:
                while True:
                    chunk = await field.read_chunk(size=64 * 1024)
                    if not chunk:
                        break
                    actual_size += len(chunk)
                    if actual_size > MAX_UPLOAD_BYTES:
                        raise web.HTTPRequestEntityTooLarge(
                            max_size=MAX_UPLOAD_BYTES, actual_size=actual_size
                        )
                    target.write(chunk)
        else:
            if field.name is None:
                raise web.HTTPBadRequest(text="Multipart fields must be named")
            fields[field.name] = await field.text()
    if not found_video or not video_path.is_file() or video_path.stat().st_size == 0:
        raise web.HTTPBadRequest(text="Multipart field 'video' must contain a video")
    return fields


def _open_usb_camera() -> cv2.VideoCapture:
    capture = cv2.VideoCapture(USB_CAMERA_DEVICE, cv2.CAP_V4L2)
    if not capture.isOpened():
        capture.release()
        raise CameraError(f"Could not open USB camera {USB_CAMERA_DEVICE}")
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, USB_CAMERA_WIDTH)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, USB_CAMERA_HEIGHT)
    capture.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def _read_usb_preview() -> Any:
    capture = _open_usb_camera()
    try:
        ok, frame = capture.read()
        if not ok or frame is None:
            raise CameraError(f"USB camera {USB_CAMERA_DEVICE} returned no frame")
        return frame
    finally:
        capture.release()


def _read_csi_preview() -> Any:
    with tempfile.TemporaryDirectory(prefix="hailo-tracking-csi-") as temp_dir:
        image_path = Path(temp_dir) / "preview.jpg"
        command = [
            "rpicam-still",
            "--nopreview",
            "--timeout",
            "1000",
            "--camera",
            str(CSI_CAMERA_INDEX),
            "--width",
            str(CSI_CAMERA_WIDTH),
            "--height",
            str(CSI_CAMERA_HEIGHT),
            "--output",
            str(image_path),
        ]
        _run_camera_command(command, timeout=10)
        image = cv2.imread(str(image_path))
        if image is None:
            raise CameraError("CSI camera did not produce a readable preview")
        return image


def _capture_usb_clip(output_path: Path, duration_seconds: float) -> None:
    capture = _open_usb_camera()
    frame_count = 0
    captured_bytes = 0
    with tempfile.TemporaryDirectory(
        prefix="hailo-tracking-usb-", dir=output_path.parent
    ) as frame_dir:
        try:
            ok, frame = capture.read()
            if not ok or frame is None:
                raise CameraError(f"USB camera {USB_CAMERA_DEVICE} returned no frame")
            height, width = frame.shape[:2]
            if width * height > MAX_FRAME_PIXELS:
                raise CameraError(
                    f"Camera frames may not exceed {MAX_FRAME_PIXELS:,} pixels"
                )
            started = time.monotonic()
            while True:
                frame_path = Path(frame_dir) / f"frame-{frame_count:04d}.jpg"
                if not cv2.imwrite(
                    str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
                ):
                    raise CameraError("Could not save a USB camera frame")
                captured_bytes += frame_path.stat().st_size
                if captured_bytes > MAX_UPLOAD_BYTES:
                    raise CameraError(
                        f"Camera clip exceeds the {MAX_UPLOAD_BYTES}-byte limit"
                    )
                frame_count += 1
                if frame_count > MAX_VIDEO_FRAMES:
                    raise CameraError(
                        f"Camera clip exceeds the {MAX_VIDEO_FRAMES}-frame limit"
                    )
                if time.monotonic() - started >= duration_seconds:
                    break
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise CameraError(
                        f"USB camera {USB_CAMERA_DEVICE} stopped during capture"
                    )
        finally:
            capture.release()

        if frame_count == 0:
            raise CameraError("USB camera did not produce a video clip")

        output_width = width + (width % 2)
        output_height = height + (height % 2)
        output_fps = frame_count / duration_seconds
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            output_fps,
            (output_width, output_height),
        )
        if not writer.isOpened():
            writer.release()
            raise CameraError("OpenCV could not create the USB camera capture MP4")
        try:
            for frame_index in range(frame_count):
                frame_path = Path(frame_dir) / f"frame-{frame_index:04d}.jpg"
                saved_frame = cv2.imread(str(frame_path))
                if saved_frame is None:
                    raise CameraError("Could not reload a captured USB camera frame")
                if (width, height) != (output_width, output_height):
                    saved_frame = cv2.copyMakeBorder(
                        saved_frame,
                        0,
                        output_height - height,
                        0,
                        output_width - width,
                        cv2.BORDER_CONSTANT,
                        value=(0, 0, 0),
                    )
                writer.write(saved_frame)
        finally:
            writer.release()
    if frame_count == 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        raise CameraError("USB camera did not produce a video clip")


def _capture_csi_clip(output_path: Path, duration_seconds: float) -> None:
    command = [
        "rpicam-vid",
        "--nopreview",
        "--timeout",
        str(int(duration_seconds * 1000)),
        "--camera",
        str(CSI_CAMERA_INDEX),
        "--width",
        str(CSI_CAMERA_WIDTH),
        "--height",
        str(CSI_CAMERA_HEIGHT),
        "--framerate",
        str(CAMERA_FPS),
        "--codec",
        "libav",
        "--libav-format",
        "mp4",
        "--output",
        str(output_path),
    ]
    _run_camera_command(command, timeout=duration_seconds + 15)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise CameraError("CSI camera did not produce a video clip")


def _run_camera_command(command: list[str], timeout: float) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise CameraError(f"Required camera command is unavailable: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CameraError(f"Camera command timed out: {command[0]}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CameraError(
            f"{command[0]} exited with status {result.returncode}: {detail}"
        )


def _jpeg_response(frame: Any) -> web.Response:
    height, width = frame.shape[:2]
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise web.HTTPInternalServerError(text="Could not encode preview frame")
    return web.Response(
        body=encoded.tobytes(),
        content_type="image/jpeg",
        headers={"X-Image-Width": str(width), "X-Image-Height": str(height)},
    )


def _video_response(output_path: Path, result: Any) -> web.Response:
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return web.json_response(
            {"error": "Tracking completed without producing an MP4"}, status=500
        )
    size = output_path.stat().st_size
    if size > MAX_OUTPUT_BYTES:
        return web.json_response(
            {"error": f"Output MP4 exceeds the {MAX_OUTPUT_BYTES}-byte limit"},
            status=500,
        )
    metadata = json.dumps(result.as_dict(), separators=(",", ":"))
    return web.Response(
        body=output_path.read_bytes(),
        content_type="video/mp4",
        headers={"X-Tracking-Metadata": metadata},
    )


async def _close_service(app: web.Application) -> None:
    await app[SERVICE_KEY].close()


def create_app(service: TrackingService | None = None) -> web.Application:
    app = web.Application(client_max_size=MAX_UPLOAD_BYTES + 1024 * 1024)
    app[SERVICE_KEY] = service or TrackingService()
    app.router.add_get("/health", health)
    app.router.add_get("/health/ready", readiness)
    app.router.add_get("/v1/info", info)
    app.router.add_post("/v1/video/preview", preview_video)
    app.router.add_post("/v1/camera/preview", preview_camera)
    app.router.add_post("/v1/track/video", track_video)
    app.router.add_post("/v1/track/camera", track_camera)
    app.on_cleanup.append(_close_service)
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    web.run_app(
        create_app(),
        host=os.environ.get("HAILO_TRACKING_HOST", DEFAULT_HOST),
        port=int(os.environ.get("HAILO_TRACKING_PORT", str(DEFAULT_PORT))),
    )
