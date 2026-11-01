import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from hailo_vision_server import decode_image_from_url, preprocess_image_for_vlm


class ImagePreprocessingTests(unittest.TestCase):
    def test_decoded_rgb_image_preserves_color_channels(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vision-rgb-") as directory:
            image_path = Path(directory) / "red.png"
            Image.new("RGB", (512, 512), (255, 0, 0)).save(image_path)

            decoded = decode_image_from_url(str(image_path))
            processed = preprocess_image_for_vlm(decoded)

        self.assertTrue(np.all(processed[:, :, 0] == 255))
        self.assertTrue(np.all(processed[:, :, 1] == 0))
        self.assertTrue(np.all(processed[:, :, 2] == 0))

    def test_rgba_input_is_converted_without_swapping_channels(self) -> None:
        rgba = np.full((32, 32, 4), (255, 0, 0, 128), dtype=np.uint8)

        processed = preprocess_image_for_vlm(rgba, target_size=(32, 32))

        self.assertTrue(np.all(processed[:, :, 0] == 255))
        self.assertTrue(np.all(processed[:, :, 1] == 0))
        self.assertTrue(np.all(processed[:, :, 2] == 0))


if __name__ == "__main__":
    unittest.main()
