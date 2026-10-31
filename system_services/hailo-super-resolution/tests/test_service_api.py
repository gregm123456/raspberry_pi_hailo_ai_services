from __future__ import annotations

import base64
import io
import unittest

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from hailo_super_resolution_service import create_app, decode_image_data_uri


class SuperResolutionAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = TestClient(TestServer(create_app("/tmp/spanf_x4.hef")))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_health_reports_model_contract(self) -> None:
        response = await self.client.get("/health")
        payload = await response.json()

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["model"], "spanf_x4")
        self.assertEqual(payload["input_shape"], [512, 512, 3])
        self.assertEqual(payload["scale_factor"], 4)

    async def test_invalid_image_returns_bad_request(self) -> None:
        response = await self.client.post(
            "/v1/super-resolve",
            json={"image": "not-an-image"},
        )
        payload = await response.json()

        self.assertEqual(response.status, 400)
        self.assertIn("error", payload)

    def test_decodes_image_data_uri_as_rgb(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGBA", (3, 2), (25, 50, 75, 120)).save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        image = decode_image_data_uri(f"data:image/png;base64,{encoded}")

        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (3, 2))


if __name__ == "__main__":
    unittest.main()
