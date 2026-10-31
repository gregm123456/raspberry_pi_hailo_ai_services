from __future__ import annotations

import base64
import unittest

import numpy as np
from PIL import Image

from super_resolution import (
    INPUT_SIZE,
    MAX_INPUT_PIXELS,
    OUTPUT_SIZE,
    SuperResolutionPipeline,
    _tile_starts,
)


class FakeDeviceClient:
    def __init__(self, **_: object) -> None:
        self.inference_count = 0
        output = np.full((OUTPUT_SIZE, OUTPUT_SIZE, 3), 64, dtype=np.uint8)
        self.output_payload = {
            "dtype": "uint8",
            "shape": list(output.shape),
            "data_b64": base64.b64encode(output.tobytes()).decode("ascii"),
        }

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def infer(self, model_path: str, input_data: dict, **kwargs: object) -> dict:
        self.inference_count += 1
        input_tensor = input_data["input"]
        self.assert_input(input_tensor, kwargs)
        return {"result": {"outputs": {"output": self.output_payload}}}

    @staticmethod
    def assert_input(input_tensor: dict, kwargs: dict) -> None:
        if input_tensor["dtype"] != "uint8":
            raise AssertionError("Expected uint8 input")
        if input_tensor["shape"] != [INPUT_SIZE, INPUT_SIZE, 3]:
            raise AssertionError("Expected a 512x512 RGB tile")
        if kwargs.get("model_type") != "tensor":
            raise AssertionError("Expected generic tensor inference")
        if kwargs.get("model_params") != {
            "input_format": "UINT8",
            "output_format": "UINT8",
        }:
            raise AssertionError("Expected uint8 model formats")


class FakeClientFactory:
    def __init__(self) -> None:
        self.client: FakeDeviceClient | None = None

    def __call__(self, **kwargs: object) -> FakeDeviceClient:
        self.client = FakeDeviceClient(**kwargs)
        return self.client


class SuperResolutionPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_square_512_image_uses_one_tile_and_returns_four_x(self) -> None:
        factory = FakeClientFactory()
        pipeline = SuperResolutionPipeline("/tmp/spanf_x4.hef", factory)

        output, tile_count = await pipeline.upscale(Image.new("RGB", (512, 512)))

        self.assertEqual((output.width, output.height), (2048, 2048))
        self.assertEqual(tile_count, 1)
        self.assertEqual(factory.client.inference_count, 1)
        self.assertEqual(output.getpixel((1024, 1024)), (64, 64, 64))

    async def test_non_square_small_image_preserves_aspect_ratio(self) -> None:
        factory = FakeClientFactory()
        pipeline = SuperResolutionPipeline("/tmp/spanf_x4.hef", factory)

        output, tile_count = await pipeline.upscale(Image.new("RGB", (300, 200)))

        self.assertEqual((output.width, output.height), (1200, 800))
        self.assertEqual(tile_count, 1)

    async def test_overlapping_tiles_cover_non_multiple_dimensions(self) -> None:
        factory = FakeClientFactory()
        pipeline = SuperResolutionPipeline("/tmp/spanf_x4.hef", factory)

        output, tile_count = await pipeline.upscale(Image.new("RGB", (513, 513)))

        self.assertEqual((output.width, output.height), (2052, 2052))
        self.assertEqual(tile_count, 4)
        self.assertGreater(min(output.getpixel((x, y))[0] for x, y in ((0, 0), (2051, 0), (0, 2051), (2051, 2051))), 0)

    def test_tile_grid_supports_common_1024_inputs(self) -> None:
        self.assertEqual(_tile_starts(1024), [0, 448, 896])

    async def test_1024_square_image_uses_overlapping_tiles(self) -> None:
        factory = FakeClientFactory()
        pipeline = SuperResolutionPipeline("/tmp/spanf_x4.hef", factory)

        output, tile_count = await pipeline.upscale(Image.new("RGB", (1024, 1024)))

        self.assertEqual((output.width, output.height), (4096, 4096))
        self.assertEqual(tile_count, 9)

    async def test_rejects_images_over_the_pixel_limit(self) -> None:
        pipeline = SuperResolutionPipeline("/tmp/spanf_x4.hef", FakeClientFactory())
        image = Image.new("RGB", (MAX_INPUT_PIXELS + 1, 1))

        with self.assertRaisesRegex(ValueError, "limit"):
            await pipeline.upscale(image)


if __name__ == "__main__":
    unittest.main()
