import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from tracking_pipeline import (
    BYTETRACK_OUTPUT_GROUPS,
    ByteTrackAssociator,
    TrackingPipeline,
    decode_bytetrack_detections,
    encode_tensor,
    map_stark_box,
    sample_target,
    validate_initial_box,
)


class FakeCapture:
    def __init__(self, frames: list[np.ndarray], fps: float = 15.0) -> None:
        self.frames = frames
        self.fps = fps
        self.index = 0
        self.released = False

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index]
        self.index += 1
        return True, frame.copy()

    def get(self, property_id: int) -> float:
        if property_id == cv2.CAP_PROP_FPS:
            return self.fps
        return 0.0

    def release(self) -> None:
        self.released = True


class FakeStarkClient:
    def __init__(self) -> None:
        self.calls = 0

    async def infer(
        self,
        model_path: str,
        input_data: dict,
        model_type: str = "tensor",
        model_params: dict | None = None,
    ) -> dict:
        self.calls += 1
        self.asserted_inputs = set(input_data["inputs"])
        self.asserted_shapes = {
            name: tuple(payload["shape"])
            for name, payload in input_data["inputs"].items()
        }
        box = np.asarray([[[0.25], [0.25], [0.75], [0.75]]], dtype=np.float32)
        return {
            "result": {
                "outputs": {
                    "stark_lightning_repvgg_a0/mul_and_add2": encode_tensor(box)
                }
            },
            "inference_time_ms": 2.0,
        }


class FakeByteTrackClient:
    async def infer(
        self,
        model_path: str,
        input_data: dict,
        model_type: str = "tensor",
        model_params: dict | None = None,
    ) -> dict:
        self.input_shape = tuple(input_data["input"]["shape"])
        outputs = {}
        for box_name, objectness_name, class_name, stride in BYTETRACK_OUTPUT_GROUPS:
            height, width = 608 // stride, 1088 // stride
            outputs[f"bytetrack/{box_name}"] = encode_tensor(
                np.zeros((1, height, width, 4), dtype=np.float32)
            )
            outputs[f"bytetrack/{objectness_name}"] = encode_tensor(
                np.zeros((1, height, width, 1), dtype=np.float32)
            )
            outputs[f"bytetrack/{class_name}"] = encode_tensor(
                np.zeros((1, height, width, 1), dtype=np.float32)
            )
        return {"result": {"outputs": outputs}, "inference_time_ms": 1.0}


class TrackingPipelineTests(unittest.TestCase):
    def test_sample_target_preserves_crop_size_at_image_edges(self) -> None:
        image = np.zeros((80, 100, 3), dtype=np.uint8)
        image[0:20, 0:20] = 255

        crop, resize_factor, origin = sample_target(
            image, (0, 0, 20, 20), area_factor=2.0, output_size=128
        )

        self.assertEqual(crop.shape, (128, 128, 3))
        self.assertGreater(resize_factor, 0)
        self.assertLess(origin[0], 0)
        self.assertLess(origin[1], 0)
        self.assertTrue(np.any(crop))

    def test_stark_box_maps_back_to_original_frame(self) -> None:
        box = np.asarray([30.0, 40.0, 50.0, 30.0])
        image = np.zeros((180, 240, 3), dtype=np.uint8)
        _, resize_factor, origin = sample_target(
            image, box, area_factor=5.0, output_size=320
        )
        crop_size = 320.0 / resize_factor
        normalized = np.asarray(
            [
                (box[0] - origin[0]) / crop_size,
                (box[1] - origin[1]) / crop_size,
                (box[0] + box[2] - origin[0]) / crop_size,
                (box[1] + box[3] - origin[1]) / crop_size,
            ]
        )

        mapped = map_stark_box(
            normalized, box, resize_factor, origin, image.shape[0], image.shape[1]
        )

        np.testing.assert_allclose(mapped, box, atol=1.0)

    def test_initial_box_must_fit_first_frame(self) -> None:
        with self.assertRaisesRegex(ValueError, "must fit inside"):
            validate_initial_box((10, 10, 40, 40), width=48, height=48)

    def test_decode_bytetrack_outputs_from_all_feature_scales(self) -> None:
        outputs = {}
        for box_name, objectness_name, class_name, stride in BYTETRACK_OUTPUT_GROUPS:
            height, width = 608 // stride, 1088 // stride
            boxes = np.zeros((1, height, width, 4), dtype=np.float32)
            objectness = np.zeros((1, height, width, 1), dtype=np.float32)
            class_scores = np.zeros((1, height, width, 1), dtype=np.float32)
            if stride == 32:
                boxes[0, 5, 10] = (0.5, 0.5, np.log(2.0), np.log(2.0))
                objectness[0, 5, 10, 0] = 0.9
                class_scores[0, 5, 10, 0] = 0.9
            outputs[f"bytetrack/{box_name}"] = encode_tensor(boxes)
            outputs[f"bytetrack/{objectness_name}"] = encode_tensor(objectness)
            outputs[f"bytetrack/{class_name}"] = encode_tensor(class_scores)

        detections = decode_bytetrack_detections(
            outputs, scale=2.0, original_width=544, original_height=304
        )

        self.assertEqual(detections.shape, (1, 5))
        self.assertAlmostEqual(float(detections[0, 4]), 0.81, places=5)
        self.assertTrue(np.all(detections[0, :4] >= 0))

    def test_bytetrack_associates_low_score_detections_with_existing_id(self) -> None:
        tracker = ByteTrackAssociator()
        first = tracker.update(np.asarray([[10, 10, 40, 60, 0.9]], dtype=np.float32))
        second = tracker.update(np.asarray([[11, 10, 41, 60, 0.2]], dtype=np.float32))
        tracker.update(np.empty((0, 5), dtype=np.float32))
        reacquired = tracker.update(
            np.asarray([[12, 10, 42, 60, 0.9]], dtype=np.float32)
        )

        self.assertEqual([track.track_id for track in first], [1])
        self.assertEqual([track.track_id for track in second], [1])
        self.assertEqual([track.track_id for track in reacquired], [1])

    def test_process_capture_runs_stark_after_template_frame(self) -> None:
        frames = [
            np.zeros((64, 80, 3), dtype=np.uint8),
            np.full((64, 80, 3), 30, dtype=np.uint8),
            np.full((64, 80, 3), 60, dtype=np.uint8),
        ]
        capture = FakeCapture(frames)
        client = FakeStarkClient()
        pipeline = TrackingPipeline(client, "/tmp/stark.hef", "/tmp/bytetrack.hef")

        async def run() -> None:
            with tempfile.TemporaryDirectory(prefix="hailo-tracking-test-") as tmp:
                output_path = Path(tmp) / "tracked.mp4"
                result = await pipeline.process_capture(
                    capture, output_path, "stark", initial_box=(20, 15, 20, 20)
                )
                self.assertEqual(result.frames_processed, 3)
                self.assertEqual(result.track_ids, {1})
                self.assertEqual(client.calls, 2)
                self.assertEqual(
                    client.asserted_shapes,
                    {
                        "stark_lightning_repvgg_a0/input_layer1": (128, 128, 3),
                        "stark_lightning_repvgg_a0/input_layer2": (320, 320, 3),
                    },
                )
                self.assertTrue(capture.released)
                self.assertGreater(output_path.stat().st_size, 0)
                output_capture = cv2.VideoCapture(str(output_path))
                try:
                    self.assertTrue(output_capture.isOpened())
                    self.assertTrue(output_capture.read()[0])
                finally:
                    output_capture.release()

        import asyncio

        asyncio.run(run())

    def test_bytetrack_inference_uses_unbatched_hef_input_shape(self) -> None:
        client = FakeByteTrackClient()
        pipeline = TrackingPipeline(client, "/tmp/stark.hef", "/tmp/bytetrack.hef")

        async def run() -> None:
            detections, elapsed = await pipeline._bytetrack_step(
                np.zeros((240, 320, 3), dtype=np.uint8)
            )
            self.assertEqual(detections.shape, (0, 5))
            self.assertEqual(elapsed, 1.0)

        import asyncio

        asyncio.run(run())
        self.assertEqual(client.input_shape, (608, 1088, 3))

if __name__ == "__main__":
    unittest.main()
