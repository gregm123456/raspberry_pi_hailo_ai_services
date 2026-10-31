import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
import cv2
import numpy as np
from aiohttp.test_utils import TestClient, TestServer

import hailo_tracking_service


class FakeDeviceClient:
    async def ping(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None


class FakePipeline:
    async def process_capture(
        self,
        capture: cv2.VideoCapture,
        output_path: Path,
        mode: str,
        initial_box: tuple[float, float, float, float] | None = None,
    ) -> SimpleNamespace:
        ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            raise RuntimeError("test video did not contain a frame")
        height, width = frame.shape[:2]
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            15.0,
            (width, height),
        )
        writer.write(frame)
        writer.release()
        return SimpleNamespace(
            as_dict=lambda: {
                "mode": mode,
                "frames_processed": 1,
                "width": width,
                "height": height,
                "output_width": width,
                "output_height": height,
                "source_fps": 15.0,
                "inference_time_ms": 1.0,
                "unique_tracks": 1,
            }
        )


class FakeTrackingService:
    def __init__(self) -> None:
        self.client = FakeDeviceClient()
        self.pipeline = FakePipeline()
        self.process_lock = asyncio.Lock()
        self.camera_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.disconnect()


class FakeCameraCapture:
    def __init__(self) -> None:
        self.frames = [
            np.full((48, 64, 3), index, dtype=np.uint8)
            for index in range(3)
        ]
        self.index = 0
        self.released = False

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index]
        self.index += 1
        return True, frame.copy()

    def release(self) -> None:
        self.released = True


class FakeCameraWriter:
    def __init__(self, path: str, _codec: int, fps: float, _size: tuple[int, int]) -> None:
        self.path = Path(path)
        self.fps = fps
        self.frames = []
        self.path.write_bytes(b"mp4")
        self.released = False

    def isOpened(self) -> bool:
        return True

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())

    def release(self) -> None:
        self.released = True


class TrackingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="tracking-api-test-")
        self.video_path = Path(self.temp_dir.name) / "input.mp4"
        writer = cv2.VideoWriter(
            str(self.video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            15.0,
            (64, 48),
        )
        writer.write(np.full((48, 64, 3), 80, dtype=np.uint8))
        writer.release()
        self.client = TestClient(TestServer(hailo_tracking_service.create_app(
            FakeTrackingService()
        )))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.temp_dir.cleanup()

    def _video_form(self) -> aiohttp.FormData:
        form = aiohttp.FormData()
        form.add_field(
            "video",
            self.video_path.read_bytes(),
            filename="input.mp4",
            content_type="video/mp4",
        )
        return form

    async def test_health_and_info_routes(self) -> None:
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["service"], "hailo-tracking")

        response = await self.client.get("/v1/info")
        payload = await response.json()
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["sources"]["video_upload"])

    async def test_readiness_reports_missing_model_files(self) -> None:
        with (
            patch.object(hailo_tracking_service, "STARK_MODEL_PATH", "/missing/stark.hef"),
            patch.object(
                hailo_tracking_service,
                "BYTETRACK_MODEL_PATH",
                "/missing/bytetrack.hef",
            ),
        ):
            response = await self.client.get("/health/ready")

        self.assertEqual(response.status, 503)
        payload = await response.json()
        self.assertEqual(len(payload["missing_models"]), 2)

    async def test_video_preview_returns_jpeg(self) -> None:
        response = await self.client.post(
            "/v1/video/preview", data=self._video_form()
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "image/jpeg")
        self.assertTrue((await response.read()).startswith(b"\xff\xd8"))
        self.assertEqual(response.headers["X-Image-Width"], "64")

    async def test_usb_camera_preview_returns_jpeg(self) -> None:
        frame = np.full((48, 64, 3), 80, dtype=np.uint8)
        with patch.object(hailo_tracking_service, "_read_usb_preview", return_value=frame):
            response = await self.client.post(
                "/v1/camera/preview?source=usb"
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "image/jpeg")

    async def test_camera_tracking_records_before_processing(self) -> None:
        def copy_test_video(output_path: Path, duration_seconds: float) -> None:
            self.assertEqual(duration_seconds, 2.0)
            shutil.copyfile(self.video_path, output_path)

        with patch.object(
            hailo_tracking_service, "_capture_usb_clip", side_effect=copy_test_video
        ):
            response = await self.client.post(
                "/v1/track/camera",
                json={
                    "source": "usb",
                    "mode": "bytetrack",
                    "duration_seconds": 2,
                },
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "video/mp4")

    def test_usb_capture_duration_starts_after_camera_warmup(self) -> None:
        capture = FakeCameraCapture()
        with tempfile.TemporaryDirectory(prefix="tracking-camera-test-") as directory:
            output_path = Path(directory) / "camera.mp4"
            created_writers = []

            def create_writer(
                path: str, codec: int, fps: float, size: tuple[int, int]
            ) -> FakeCameraWriter:
                writer = FakeCameraWriter(path, codec, fps, size)
                created_writers.append(writer)
                return writer

            with (
                patch.object(hailo_tracking_service, "_open_usb_camera", return_value=capture),
                patch.object(cv2, "VideoWriter", side_effect=create_writer),
                patch.object(
                    hailo_tracking_service.time,
                    "monotonic",
                    side_effect=[0.0, 0.1, 0.9, 1.1],
                ),
            ):
                hailo_tracking_service._capture_usb_clip(output_path, 1.0)

        writer = created_writers[0]
        self.assertEqual(len(writer.frames), 3)
        self.assertEqual(writer.fps, 3.0)
        self.assertTrue(capture.released)
        self.assertTrue(writer.released)

    async def test_invalid_tracking_mode_is_rejected(self) -> None:
        form = self._video_form()
        form.add_field("mode", "unknown")

        response = await self.client.post("/v1/track/video", data=form)

        self.assertEqual(response.status, 400)
        self.assertIn("mode must be", await response.text())

    async def test_stark_requires_a_complete_initial_box(self) -> None:
        form = self._video_form()
        form.add_field("mode", "stark")
        form.add_field("x", "10")

        response = await self.client.post("/v1/track/video", data=form)

        self.assertEqual(response.status, 400)
        self.assertIn("numeric x, y, width, and height", await response.text())

    async def test_track_video_returns_mp4_and_metadata(self) -> None:
        form = self._video_form()
        form.add_field("mode", "stark")
        for name, value in zip(("x", "y", "width", "height"), (10, 10, 20, 20)):
            form.add_field(name, str(value))

        response = await self.client.post("/v1/track/video", data=form)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "video/mp4")
        self.assertGreater(len(await response.read()), 0)
        self.assertEqual(
            json.loads(response.headers["X-Tracking-Metadata"])["frames_processed"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
