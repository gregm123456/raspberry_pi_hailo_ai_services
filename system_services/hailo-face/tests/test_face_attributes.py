import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from hailo_face_service import create_app
from face_attributes import (
    FaceAttributePipeline,
    _encode_tensor,
    decode_mivolo_output,
    postprocess_scrfd,
    prepare_mivolo_face_input,
)


def _scrfd_outputs() -> dict[str, dict]:
    outputs = {}
    for level, (height, width) in enumerate(((48, 80), (24, 40), (12, 20))):
        boxes = np.zeros((1, height, width, 8), dtype=np.float32)
        scores = np.zeros((1, height, width, 2), dtype=np.float32)
        landmarks = np.zeros((1, height, width, 20), dtype=np.float32)
        if level == 0:
            boxes[0, 3, 2, :4] = 1.0
            scores[0, 3, 2, 0] = 0.9
        outputs[f"box_{level}"] = _encode_tensor(boxes)
        outputs[f"score_{level}"] = _encode_tensor(scores)
        outputs[f"landmark_{level}"] = _encode_tensor(landmarks)
    return outputs


class FakeDeviceClient:
    def __init__(self, timeout: int) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def infer(self, model_path, input_data, model_type, model_params):
        if model_path.endswith("scrfd.hef"):
            self.assert_shape(input_data, (384, 640, 3))
            result = {"outputs": _scrfd_outputs()}
        else:
            self.assert_shape(input_data, (224, 224, 6))
            result = {
                "outputs": {
                    "mivolo": _encode_tensor(
                        np.asarray([[[2.0, 0.0, 44.6]]], dtype=np.float32)
                    )
                }
            }
        return {"result": result, "inference_time_ms": 1}

    @staticmethod
    def assert_shape(input_data, shape) -> None:
        if tuple(input_data["input"]["shape"]) != shape:
            raise AssertionError(f"Expected input shape {shape}")


class FaceAttributeTests(unittest.TestCase):
    def test_decodes_scrfd_boxes_and_landmarks(self) -> None:
        faces = postprocess_scrfd(_scrfd_outputs(), original_size=(640, 384))
        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0]["bbox"], [8, 16, 16, 16])
        self.assertAlmostEqual(faces[0]["confidence"], 0.9)
        self.assertEqual(len(faces[0]["landmarks"]), 5)

    def test_prepares_face_only_six_channel_input(self) -> None:
        image = np.full((10, 20, 3), 127, dtype=np.uint8)
        tensor, crop = prepare_mivolo_face_input(image, [0, 0, 20, 10])
        self.assertEqual(tensor.shape, (224, 224, 6))
        self.assertTrue(np.all(tensor[..., 3:] == 0))
        self.assertEqual(crop.shape, (10, 20, 3))
        self.assertGreater(float(tensor[..., :3].sum()), 0)

    def test_decodes_mivolo_logits(self) -> None:
        result = decode_mivolo_output(
            {"output": _encode_tensor(np.asarray([[[2.0, 0.0, 44.6]]], dtype=np.float32))}
        )
        self.assertEqual(result["age_years"], 44.6)
        self.assertEqual(result["gender"], "male")
        self.assertAlmostEqual(result["gender_scores"]["male"], 0.8808, places=3)

    def test_analyzes_image_using_both_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scrfd = Path(directory) / "scrfd.hef"
            mivolo = Path(directory) / "mivolo.hef"
            scrfd.touch()
            mivolo.touch()
            pipeline = FaceAttributePipeline(
                str(scrfd), str(mivolo), client_factory=FakeDeviceClient
            )
            result = pipeline.analyze(Image.new("RGB", (640, 384), color="white"))

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["faces"][0]["gender"], "male")
        self.assertEqual(result["faces"][0]["age_years"], 44.6)
        self.assertTrue(result["faces"][0]["crop"].startswith("data:image/jpeg;base64,"))

    def test_attributes_route_returns_model_result(self) -> None:
        class FakeConfig:
            face_recognition = {}
            database = {"enabled": False}
            face_attributes = {
                "enabled": True,
                "scrfd_hef": "/not-used/scrfd.hef",
                "mivolo_hef": "/not-used/mivolo.hef",
            }

        class FakePipeline:
            def __init__(self, **kwargs) -> None:
                pass

            def analyze(self, image: Image.Image) -> dict:
                return {"model": "fake", "count": 0, "faces": []}

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="white").save(buffer, format="JPEG")
        image_uri = "data:image/jpeg;base64," + base64.b64encode(
            buffer.getvalue()
        ).decode("ascii")
        with patch("hailo_face_service.FaceAttributePipeline", FakePipeline):
            app = create_app(FakeConfig())
        response = app.test_client().post(
            "/v1/attributes", json={"image": image_uri}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["model"], "fake")

    def test_attributes_route_rejects_missing_image(self) -> None:
        class FakeConfig:
            face_recognition = {}
            database = {"enabled": False}
            face_attributes = {"enabled": True}

        app = create_app(FakeConfig())
        response = app.test_client().post("/v1/attributes", json={})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
