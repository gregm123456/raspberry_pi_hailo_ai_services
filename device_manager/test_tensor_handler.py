import tempfile
import unittest

import numpy as np

from hailo_device_manager import TensorHandler, decode_tensor, encode_tensor


class FakeBuffer:
    def __init__(self) -> None:
        self.value = None

    def set_buffer(self, value: np.ndarray) -> None:
        self.value = value


class FakeBindings:
    def __init__(self, output_names: list[str], input_names: list[str]) -> None:
        self.input_buffers = {name: FakeBuffer() for name in input_names}
        self.output_buffers = {name: FakeBuffer() for name in output_names}

    def input(self, name: str | None = None) -> FakeBuffer:
        if name is None:
            return next(iter(self.input_buffers.values()))
        return self.input_buffers[name]

    def output(self, name: str | None = None) -> FakeBuffer:
        if name is None:
            return next(iter(self.output_buffers.values()))
        return self.output_buffers[name]


class FakeJob:
    def wait(self, timeout_ms: int) -> None:
        return None


class FakeConfiguredModel:
    def __init__(self, output_names: list[str], input_names: list[str]) -> None:
        self.output_names = output_names
        self.input_names = input_names

    def create_bindings(self) -> FakeBindings:
        return FakeBindings(self.output_names, self.input_names)

    def wait_for_async_ready(self, timeout_ms: int) -> None:
        return None

    def run_async(self, bindings_list: list[FakeBindings]) -> FakeJob:
        bindings = bindings_list[0]
        for index, output in enumerate(bindings.output_buffers.values(), start=1):
            output.value.fill(index)
        return FakeJob()

    def release(self) -> None:
        return None


class FakeInput:
    def __init__(self, name: str, shape: tuple[int, ...]) -> None:
        self.name = name
        self.shape = shape

    def set_format_type(self, value: object) -> None:
        self.format_type = value


class FakeOutput:
    def __init__(self, name: str, shape: tuple[int, ...]) -> None:
        self.name = name
        self.shape = shape

    def set_format_type(self, value: object) -> None:
        self.format_type = value


class FakeInferModel:
    def __init__(
        self,
        input_shapes: list[tuple[str, tuple[int, ...]]],
        output_shapes: list[tuple[str, tuple[int, ...]]],
    ) -> None:
        self._inputs = [FakeInput(name, shape) for name, shape in input_shapes]
        self._outputs = [FakeOutput(name, shape) for name, shape in output_shapes]
        self.configured_model = FakeConfiguredModel(
            [output.name for output in self._outputs],
            [input_info.name for input_info in self._inputs],
        )

    def inputs(self) -> list[FakeInput]:
        return self._inputs

    def input(self, name: str | None = None) -> FakeInput:
        if name is None:
            return self._inputs[0]
        return next(input_info for input_info in self._inputs if input_info.name == name)

    def outputs(self) -> list[FakeOutput]:
        return self._outputs

    def output(self, name: str | None = None) -> FakeOutput:
        if name is None:
            return self._outputs[0]
        return next(output for output in self._outputs if output.name == name)

    def configure(self) -> FakeConfiguredModel:
        return self.configured_model

    def release(self) -> None:
        return None


class FakeVDevice:
    def __init__(
        self,
        input_shapes: list[tuple[str, tuple[int, ...]]] | None = None,
        output_shapes: list[tuple[str, tuple[int, ...]]] | None = None,
    ) -> None:
        if input_shapes is None:
            input_shapes = [("input", (1, 2, 2, 3))]
        if output_shapes is None:
            output_shapes = [
                ("boxes", (1, 1, 4)),
                ("scores", (1, 1, 2)),
            ]
        self.infer_model = FakeInferModel(input_shapes, output_shapes)

    def create_infer_model(self, model_path: str) -> FakeInferModel:
        return self.infer_model


class TensorHandlerTests(unittest.TestCase):
    def test_runs_single_input_and_encodes_every_output(self) -> None:
        with tempfile.NamedTemporaryFile() as model_file:
            handler = TensorHandler()
            runtime = handler.load(FakeVDevice(), model_file.name, {})

        input_tensor = np.ones(runtime.input_shape, dtype=np.float32)
        result = handler.infer(runtime, {"input": encode_tensor(input_tensor)})

        self.assertEqual(set(result["outputs"]), {"boxes", "scores"})
        self.assertTrue(
            np.all(decode_tensor(result["outputs"]["boxes"]) == 1)
        )
        self.assertTrue(
            np.all(decode_tensor(result["outputs"]["scores"]) == 2)
        )

    def test_rejects_input_shape_mismatch(self) -> None:
        with tempfile.NamedTemporaryFile() as model_file:
            handler = TensorHandler()
            runtime = handler.load(FakeVDevice(), model_file.name, {})

        with self.assertRaisesRegex(ValueError, "does not match HEF shape"):
            handler.infer(
                runtime,
                {"input": encode_tensor(np.zeros((1, 3, 2, 3), dtype=np.uint8))},
            )

    def test_rejects_unknown_host_tensor_formats(self) -> None:
        with tempfile.NamedTemporaryFile() as model_file:
            with self.assertRaisesRegex(ValueError, "tensor format"):
                TensorHandler().load(
                    FakeVDevice(),
                    model_file.name,
                    {"input_format": "INT8"},
                )

    def test_runs_single_output_hef(self) -> None:
        with tempfile.NamedTemporaryFile() as model_file:
            handler = TensorHandler()
            runtime = handler.load(
                FakeVDevice(output_shapes=[("mivolo", (1, 1, 3))]),
                model_file.name,
                {},
            )

        result = handler.infer(
            runtime,
            {"input": encode_tensor(np.zeros(runtime.input_shape, dtype=np.uint8))},
        )
        self.assertTrue(np.all(decode_tensor(result["outputs"]["mivolo"]) == 1))

    def test_runs_named_multi_input_hef(self) -> None:
        input_shapes = [
            ("stark/input_layer2", (1, 320, 320, 3)),
            ("stark/input_layer1", (1, 128, 128, 3)),
        ]
        with tempfile.NamedTemporaryFile() as model_file:
            handler = TensorHandler()
            runtime = handler.load(
                FakeVDevice(input_shapes, [("box", (1, 4, 1))]),
                model_file.name,
                {},
            )

        payloads = {
            name: encode_tensor(np.ones(shape, dtype=np.uint8))
            for name, shape in input_shapes
        }
        result = handler.infer(runtime, {"inputs": payloads})

        self.assertEqual(runtime.input_names, [name for name, _ in input_shapes])
        self.assertEqual(runtime.input_shapes, dict(input_shapes))
        self.assertEqual(
            set(result["outputs"]),
            {"box"},
        )
        self.assertTrue(np.all(decode_tensor(result["outputs"]["box"]) == 1))

    def test_requires_exact_named_inputs_for_multi_input_hef(self) -> None:
        input_shapes = [
            ("stark/search", (1, 320, 320, 3)),
            ("stark/template", (1, 128, 128, 3)),
        ]
        with tempfile.NamedTemporaryFile() as model_file:
            handler = TensorHandler()
            runtime = handler.load(
                FakeVDevice(input_shapes, [("box", (1, 4, 1))]),
                model_file.name,
                {},
            )

        with self.assertRaisesRegex(ValueError, "Expected named inputs"):
            handler.infer(runtime, {"input": encode_tensor(np.zeros((1, 1), dtype=np.uint8))})

    def test_validates_each_named_input_shape(self) -> None:
        input_shapes = [
            ("stark/search", (1, 320, 320, 3)),
            ("stark/template", (1, 128, 128, 3)),
        ]
        with tempfile.NamedTemporaryFile() as model_file:
            handler = TensorHandler()
            runtime = handler.load(
                FakeVDevice(input_shapes, [("box", (1, 4, 1))]),
                model_file.name,
                {},
            )

        payloads = {
            "stark/search": encode_tensor(np.zeros(input_shapes[0][1], dtype=np.uint8)),
            "stark/template": encode_tensor(np.zeros((1, 127, 128, 3), dtype=np.uint8)),
        }
        with self.assertRaisesRegex(ValueError, "stark/template.*does not match HEF shape"):
            handler.infer(runtime, {"inputs": payloads})


if __name__ == "__main__":
    unittest.main()
