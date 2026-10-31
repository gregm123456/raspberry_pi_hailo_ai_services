import json
import tempfile
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestServer

from portal_client import HailoTrackingClient


class TrackingClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        app = web.Application()
        app.router.add_post("/v1/track/video", self._track_video)
        app.router.add_post("/v1/track/camera", self._track_camera)
        app.router.add_post("/v1/camera/preview", self._preview_camera)
        self.server = TestServer(app)
        await self.server.start_server()
        self.client = HailoTrackingClient(str(self.server.make_url("").with_path("")))

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def _track_video(self, request: web.Request) -> web.Response:
        reader = await request.multipart()
        fields = {}
        while field := await reader.next():
            fields[field.name] = (
                await field.read(decode=False)
                if field.name == "video"
                else await field.text()
            )
        self.assertEqual(fields["mode"], "stark")
        self.assertEqual(fields["x"], "12.5")
        return self._video_response()

    async def _track_camera(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.assertEqual(payload["source"], "usb")
        self.assertEqual(payload["mode"], "bytetrack")
        return self._video_response()

    async def _preview_camera(self, request: web.Request) -> web.Response:
        self.assertEqual(request.query["source"], "csi")
        return web.Response(body=b"jpeg-preview", content_type="image/jpeg")

    @staticmethod
    def _video_response() -> web.Response:
        return web.Response(
            body=b"tracked-mp4",
            content_type="video/mp4",
            headers={
                "X-Tracking-Metadata": json.dumps(
                    {"frames_processed": 1, "unique_tracks": 1}
                )
            },
        )

    async def test_uploaded_video_uses_multipart_and_reads_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tracking-client-test-") as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"input-mp4")

            media, metadata = await self.client.track_video(
                str(path), "stark", (12.5, 6, 20, 30)
            )

        self.assertEqual(media, b"tracked-mp4")
        self.assertEqual(metadata["frames_processed"], 1)

    async def test_camera_tracking_posts_json(self) -> None:
        media, metadata = await self.client.track_camera(
            "usb", "bytetrack", 5.0
        )

        self.assertEqual(media, b"tracked-mp4")
        self.assertEqual(metadata["unique_tracks"], 1)

    async def test_camera_preview_returns_image_bytes(self) -> None:
        image = await self.client.preview_camera("csi")

        self.assertEqual(image, b"jpeg-preview")


if __name__ == "__main__":
    unittest.main()
