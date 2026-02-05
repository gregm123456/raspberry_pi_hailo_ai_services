#!/usr/bin/env python3
"""hailo-florence: Florence-2 captioning and VQA service."""

import argparse
import base64
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image
from tokenizers import Tokenizer as TokenizerFast
from transformers import AutoProcessor
import onnxruntime as ort

try:
    from hailo_platform import VDevice, FormatType, HailoSchedulingAlgorithm
    HAILO_AVAILABLE = True
except Exception:
    HAILO_AVAILABLE = False


LOGGER = logging.getLogger("hailo-florence")

def _config_path() -> str:
    return os.environ.get(
        "FLORENCE_CONFIG",
        os.path.join(
            os.environ.get("XDG_CONFIG_HOME", "/etc/xdg"),
            "hailo-florence",
            "hailo-florence.json",
        ),
    )

START_TOKEN = 2
ENCODER_OUTPUT_KEY = "florence2_transformer_decoder/input_layer1"
DECODER_INPUT_KEY = "florence2_transformer_decoder/input_layer2"


@dataclass
class FlorenceConfig:
    server_host: str = "0.0.0.0"
    server_port: int = 11438
    log_level: str = "info"

    model_name: str = "florence-2"
    processor_name: str = "microsoft/florence-2-base"
    model_dir: str = "/var/lib/hailo-florence/models"
    vision_encoder: str = "vision_encoder.onnx"
    text_encoder: str = "florence2_transformer_encoder.hef"
    decoder: str = "florence2_transformer_decoder.hef"
    tokenizer: str = "tokenizer.json"
    caption_embedding: str = "caption_embedding.npy"
    vqa_embedding: str = "vqa_embedding.npy"
    word_embedding: str = "word_embedding.npy"
    image_size: int = 384
    max_length: int = 100
    min_length: int = 10
    temperature: float = 0.7
    max_tokens: int = 32
    max_image_bytes: int = 10 * 1024 * 1024
    timeout_ms: int = 1000

    max_concurrent_requests: int = 1
    request_timeout_seconds: int = 30

    metrics_enabled: bool = True
    metrics_retention_seconds: int = 3600

    @classmethod
    def load(cls) -> "FlorenceConfig":
        config_path = _config_path()
        if not os.path.exists(config_path):
            LOGGER.warning("Config not found at %s, using defaults", config_path)
            return cls()

        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle) or {}

        server = config.get("server", {})
        model = config.get("model", {})
        resources = config.get("resources", {})
        metrics = config.get("metrics", {})

        return cls(
            server_host=server.get("host", "0.0.0.0"),
            server_port=int(server.get("port", 11438)),
            log_level=server.get("log_level", "info"),
            model_name=model.get("name", "florence-2"),
            processor_name=model.get("processor_name", "microsoft/florence-2-base"),
            model_dir=model.get("model_dir", "/var/lib/hailo-florence/models"),
            vision_encoder=model.get("vision_encoder", "vision_encoder.onnx"),
            text_encoder=model.get("text_encoder", "florence2_transformer_encoder.hef"),
            decoder=model.get("decoder", "florence2_transformer_decoder.hef"),
            tokenizer=model.get("tokenizer", "tokenizer.json"),
            caption_embedding=model.get("caption_embedding", "caption_embedding.npy"),
            vqa_embedding=model.get("vqa_embedding", "vqa_embedding.npy"),
            word_embedding=model.get("word_embedding", "word_embedding.npy"),
            image_size=int(model.get("image_size", 384)),
            max_length=int(model.get("max_length", 100)),
            min_length=int(model.get("min_length", 10)),
            temperature=float(model.get("temperature", 0.7)),
            max_tokens=int(model.get("max_tokens", 32)),
            max_image_bytes=int(model.get("max_image_bytes", 10 * 1024 * 1024)),
            timeout_ms=int(model.get("timeout_ms", 1000)),
            max_concurrent_requests=int(resources.get("max_concurrent_requests", 1)),
            request_timeout_seconds=int(resources.get("request_timeout_seconds", 30)),
            metrics_enabled=bool(metrics.get("enabled", True)),
            metrics_retention_seconds=int(metrics.get("retention_seconds", 3600)),
        )


class FlorencePipeline:
    def __init__(self, config: FlorenceConfig) -> None:
        self.config = config
        self.model_loaded = False
        self.model_name = config.model_name
        self.model_dir = Path(config.model_dir)
        self._lock = threading.Lock()

        self._processor = None
        self._tokenizer = None
        self._word_embedding = None
        self._caption_embedding = None
        self._vqa_embedding = None
        self._davit_session = None
        self._vdevice = None
        self._encoder = None
        self._decoder = None
        self._load_error: Optional[str] = None

    def _resolve_processor_source(self) -> str:
        processor = self.config.processor_name
        if os.path.exists(processor):
            return processor

        if "/" in processor:
            local_dir = self.model_dir / "processor" / processor.replace("/", "__")
            if local_dir.exists():
                return str(local_dir)

        return processor

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def load(self) -> None:
        if not HAILO_AVAILABLE:
            raise RuntimeError(
                "HailoRT Python bindings not available. Install python3-h10-hailort."
            )

        required_files = {
            "vision_encoder": self.config.vision_encoder,
            "text_encoder": self.config.text_encoder,
            "decoder": self.config.decoder,
            "tokenizer": self.config.tokenizer,
            "caption_embedding": self.config.caption_embedding,
            "word_embedding": self.config.word_embedding,
        }

        missing = [
            name
            for name, filename in required_files.items()
            if not (self.model_dir / filename).exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Missing model files: " + ", ".join(missing)
            )

        self._processor = AutoProcessor.from_pretrained(
            self._resolve_processor_source(),
            trust_remote_code=True,
            size={"height": self.config.image_size, "width": self.config.image_size},
            crop_size={"height": self.config.image_size, "width": self.config.image_size},
        )

        ort.set_default_logger_severity(3)
        self._davit_session = ort.InferenceSession(
            str(self.model_dir / self.config.vision_encoder),
            providers=["CPUExecutionProvider"],
        )

        self._tokenizer = TokenizerFast.from_file(
            str(self.model_dir / self.config.tokenizer)
        )

        self._word_embedding = np.load(self.model_dir / self.config.word_embedding)
        self._caption_embedding = np.load(
            self.model_dir / self.config.caption_embedding
        )

        vqa_path = self.model_dir / self.config.vqa_embedding
        if vqa_path.exists():
            self._vqa_embedding = np.load(vqa_path)
        else:
            self._vqa_embedding = None

        params = VDevice.create_params()
        params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
        self._vdevice = VDevice(params)

        encoder_infer_model = self._vdevice.create_infer_model(
            str(self.model_dir / self.config.text_encoder)
        )
        encoder_infer_model.input().set_format_type(FormatType.FLOAT32)
        encoder_infer_model.output().set_format_type(FormatType.FLOAT32)
        self._encoder = encoder_infer_model.configure()

        decoder_infer_model = self._vdevice.create_infer_model(
            str(self.model_dir / self.config.decoder)
        )
        decoder_infer_model.input(ENCODER_OUTPUT_KEY).set_format_type(FormatType.FLOAT32)
        decoder_infer_model.input(DECODER_INPUT_KEY).set_format_type(FormatType.FLOAT32)
        decoder_infer_model.output().set_format_type(FormatType.FLOAT32)
        self._decoder = decoder_infer_model.configure()

        self.model_loaded = True

    def caption(self, image: Image.Image, max_length: int, min_length: int, temperature: float) -> Tuple[str, int]:
        return self._infer(image, "caption", max_length, min_length, temperature, None)

    def vqa(self, image: Image.Image, question: str, max_length: int, min_length: int, temperature: float) -> Tuple[str, int]:
        return self._infer(image, "vqa", max_length, min_length, temperature, question)

    def _infer(
        self,
        image: Image.Image,
        task: str,
        max_length: int,
        min_length: int,
        temperature: float,
        question: Optional[str],
    ) -> Tuple[str, int]:
        if not self.model_loaded:
            raise RuntimeError("Model not loaded")

        with self._lock:
            start_time = time.time()
            prompt = "<CAPTION>"
            task_embedding = self._caption_embedding

            if task == "vqa":
                if not question:
                    raise ValueError("VQA request missing question")
                if self._vqa_embedding is None:
                    raise RuntimeError("VQA embedding not configured")
                prompt = f"<VQA>{question}"
                task_embedding = self._vqa_embedding

            try:
                inputs = self._processor(
                    text=prompt,
                    images=image,
                    return_tensors="np",
                )
            except Exception:
                inputs = self._processor(
                    text=prompt,
                    images=image,
                    return_tensors="pt",
                )
            pixel_values = inputs.get("pixel_values")
            if hasattr(pixel_values, "numpy"):
                pixel_values = pixel_values.numpy()

            image_features = self._davit_session.run(
                None, {"pixel_values": pixel_values}
            )[0]

            image_text_embeddings = np.concatenate(
                [np.expand_dims(image_features, axis=0), task_embedding], axis=2
            )

            encoder_hidden_state = np.empty((1, 153, 768), dtype=np.float32)
            encoder_bindings = self._encoder.create_bindings()
            encoder_bindings.input().set_buffer(image_text_embeddings)
            encoder_bindings.output().set_buffer(encoder_hidden_state)
            encoder_job = self._encoder.run_async([encoder_bindings], lambda _: None)
            encoder_job.wait(self.config.timeout_ms)

            max_tokens = min(max_length, self.config.max_tokens)
            decoder_input = np.zeros(
                (1, 1, self.config.max_tokens, self._word_embedding.shape[1]),
                dtype=np.float32,
            )
            decoder_input[0, 0, 0, :] = self._word_embedding[START_TOKEN]

            generated_ids = [START_TOKEN]
            token_index = 0

            while token_index < max_tokens:
                decoder_output = np.empty((self.config.max_tokens, self._word_embedding.shape[0]), dtype=np.float32)
                decoder_bindings = self._decoder.create_bindings()
                decoder_bindings.input(ENCODER_OUTPUT_KEY).set_buffer(encoder_hidden_state)
                decoder_bindings.input(DECODER_INPUT_KEY).set_buffer(decoder_input)
                decoder_bindings.output().set_buffer(decoder_output)
                decoder_job = self._decoder.run_async([decoder_bindings], lambda _: None)
                decoder_job.wait(self.config.timeout_ms)

                logits = decoder_output[token_index]
                next_token = self._select_token(logits, temperature)
                generated_ids.append(next_token)

                if next_token == START_TOKEN and token_index >= min_length:
                    break

                token_index += 1
                if token_index < self.config.max_tokens:
                    decoder_input[0, 0, token_index, :] = self._word_embedding[next_token]

            caption = self._tokenizer.decode(
                np.array(generated_ids), skip_special_tokens=True
            )

            inference_time_ms = int((time.time() - start_time) * 1000)
            return caption.strip(), inference_time_ms

    @staticmethod
    def _select_token(logits: np.ndarray, temperature: float) -> int:
        if temperature <= 0.0:
            return int(np.argmax(logits))

        scaled = logits / max(temperature, 1e-5)
        scaled -= np.max(scaled)
        probs = np.exp(scaled)
        probs /= probs.sum()
        return int(np.random.choice(len(probs), p=probs))


class ServiceState:
    def __init__(self) -> None:
        self.start_time = time.time()
        self.pipeline: Optional[FlorencePipeline] = None
        self.config = FlorenceConfig()
        self.model_error: Optional[str] = None

        self.requests_total = 0
        self.requests_succeeded = 0
        self.requests_failed = 0
        self.inference_times = []

    def uptime_seconds(self) -> int:
        return int(time.time() - self.start_time)

    def record_success(self, inference_time_ms: int) -> None:
        self.requests_total += 1
        self.requests_succeeded += 1
        self.inference_times.append(inference_time_ms)
        if len(self.inference_times) > 1000:
            self.inference_times = self.inference_times[-1000:]

    def record_failure(self) -> None:
        self.requests_total += 1
        self.requests_failed += 1

    def latency_percentile(self, percentile: int) -> float:
        if not self.inference_times:
            return 0.0
        sorted_times = sorted(self.inference_times)
        idx = int(len(sorted_times) * percentile / 100)
        return float(sorted_times[min(idx, len(sorted_times) - 1)])


state = ServiceState()
app = FastAPI(title="hailo-florence", version="1.0.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    payload = detail if isinstance(detail, dict) else {"error": "error", "message": str(detail)}
    payload["status"] = exc.status_code
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.on_event("startup")
async def startup_event() -> None:
    state.config = FlorenceConfig.load()
    logging.basicConfig(
        level=state.config.log_level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    LOGGER.info("Starting hailo-florence service")
    pipeline = FlorencePipeline(state.config)
    try:
        pipeline.load()
        state.pipeline = pipeline
        state.model_error = None
        LOGGER.info("Florence-2 models loaded")
    except Exception as exc:
        state.pipeline = pipeline
        state.model_error = str(exc)
        LOGGER.error("Failed to load Florence-2 models: %s", exc)


@app.get("/health")
async def health() -> Dict[str, Any]:
    hailo_status = "connected" if os.path.exists("/dev/hailo0") else "disconnected"
    model_loaded = bool(state.pipeline and state.pipeline.model_loaded)

    payload: Dict[str, Any] = {
        "status": "healthy" if model_loaded else "unhealthy",
        "model_loaded": model_loaded,
        "uptime_seconds": state.uptime_seconds(),
        "version": "1.0.0",
        "hailo_device": hailo_status,
    }

    if state.model_error:
        payload["error"] = state.model_error

    return payload


@app.post("/v1/caption")
async def caption(request: Request) -> Dict[str, Any]:
    image, params = await parse_request(request)
    ensure_pipeline_ready()

    try:
        caption_text, inference_time_ms = state.pipeline.caption(
            image,
            max_length=params.max_length,
            min_length=params.min_length,
            temperature=params.temperature,
        )
    except RuntimeError as exc:
        state.record_failure()
        raise_api_error("model_not_ready", str(exc), 503)
    except ValueError as exc:
        state.record_failure()
        raise_api_error("invalid_parameters", str(exc), 422)
    except Exception as exc:
        state.record_failure()
        raise_api_error("inference_failed", str(exc), 500)

    state.record_success(inference_time_ms)
    return {
        "caption": caption_text,
        "inference_time_ms": inference_time_ms,
        "model": state.pipeline.model_name,
        "token_count": len(caption_text.split()),
    }


@app.post("/v1/vqa")
async def vqa(request: Request) -> Dict[str, Any]:
    image, params = await parse_request(request)
    question = params.question
    if not question:
        raise_api_error("invalid_parameters", "Missing question for VQA", 422)

    ensure_pipeline_ready()

    try:
        answer, inference_time_ms = state.pipeline.vqa(
            image,
            question=question,
            max_length=params.max_length,
            min_length=params.min_length,
            temperature=params.temperature,
        )
    except RuntimeError as exc:
        state.record_failure()
        if "VQA embedding" in str(exc):
            raise_api_error("vqa_not_configured", str(exc), 501)
        raise_api_error("model_not_ready", str(exc), 503)
    except ValueError as exc:
        state.record_failure()
        raise_api_error("invalid_parameters", str(exc), 422)
    except Exception as exc:
        state.record_failure()
        raise_api_error("inference_failed", str(exc), 500)

    state.record_success(inference_time_ms)
    return {
        "answer": answer,
        "inference_time_ms": inference_time_ms,
        "model": state.pipeline.model_name,
        "token_count": len(answer.split()),
    }


@app.get("/metrics")
async def metrics() -> Dict[str, Any]:
    if not state.config.metrics_enabled:
        raise_api_error("metrics_disabled", "Metrics collection disabled", 404)

    import psutil

    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss // 1024 // 1024
    avg_latency = (
        sum(state.inference_times) / len(state.inference_times)
        if state.inference_times
        else 0.0
    )

    return {
        "requests_total": state.requests_total,
        "requests_succeeded": state.requests_succeeded,
        "requests_failed": state.requests_failed,
        "average_inference_time_ms": avg_latency,
        "p50_inference_time_ms": state.latency_percentile(50),
        "p95_inference_time_ms": state.latency_percentile(95),
        "p99_inference_time_ms": state.latency_percentile(99),
        "memory_usage_mb": memory_mb,
        "model_cache_hit_rate": 1.0,
        "uptime_seconds": state.uptime_seconds(),
    }


@dataclass
class RequestParams:
    max_length: int
    min_length: int
    temperature: float
    question: Optional[str] = None


async def parse_request(request: Request) -> Tuple[Image.Image, RequestParams]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        image_file = form.get("image") or form.get("file")
        if image_file is None:
            raise_api_error("invalid_image_format", "Missing image file", 400)

        image_bytes = await image_file.read()
        image = decode_image_bytes(image_bytes)

        params = RequestParams(
            max_length=parse_int(form.get("max_length"), state.config.max_length),
            min_length=parse_int(form.get("min_length"), state.config.min_length),
            temperature=parse_float(form.get("temperature"), state.config.temperature),
            question=form.get("question"),
        )
        params.max_length = min(params.max_length, state.config.max_tokens)
        validate_params(params)
        if params.max_length < params.min_length:
            raise_api_error("invalid_parameters", "max_length must be >= min_length", 422)
        return image, params

    try:
        payload = await request.json()
    except Exception:
        raise_api_error("invalid_parameters", "Invalid JSON payload", 400)
    if not isinstance(payload, dict):
        raise_api_error("invalid_parameters", "JSON body must be an object", 400)

    image_data = payload.get("image")
    if not image_data:
        raise_api_error("invalid_image_format", "Missing image field", 400)

    image = decode_image_data(image_data)

    params = RequestParams(
        max_length=int(payload.get("max_length", state.config.max_length)),
        min_length=int(payload.get("min_length", state.config.min_length)),
        temperature=float(payload.get("temperature", state.config.temperature)),
        question=payload.get("question"),
    )

    params.max_length = min(params.max_length, state.config.max_tokens)
    validate_params(params)

    if params.max_length < params.min_length:
        raise_api_error("invalid_parameters", "max_length must be >= min_length", 422)

    return image, params


def decode_image_data(image_data: str) -> Image.Image:
    if not image_data.startswith("data:image/"):
        raise_api_error("invalid_image_format", "Image must be a data URI", 400)

    if ";base64," not in image_data:
        raise_api_error("invalid_image_format", "Image must be base64-encoded", 400)

    _, b64_data = image_data.split(",", 1)
    try:
        image_bytes = base64.b64decode(b64_data)
    except Exception:
        raise_api_error("invalid_image_format", "Invalid base64 payload", 400)

    return decode_image_bytes(image_bytes)


def decode_image_bytes(image_bytes: bytes) -> Image.Image:
    if len(image_bytes) > state.config.max_image_bytes:
        raise_api_error(
            "image_too_large",
            f"Image size exceeds {state.config.max_image_bytes} bytes",
            413,
        )

    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
    except Exception:
        raise_api_error("invalid_image_format", "Unable to decode image", 400)

    if image.mode != "RGB":
        image = image.convert("RGB")

    return image


def parse_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def parse_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def validate_params(params: RequestParams) -> None:
    if params.max_length <= 0:
        raise_api_error("invalid_parameters", "max_length must be > 0", 422)
    if params.min_length < 0:
        raise_api_error("invalid_parameters", "min_length must be >= 0", 422)
    if not 0.0 <= params.temperature <= 1.0:
        raise_api_error("invalid_parameters", "temperature must be 0.0-1.0", 422)


def ensure_pipeline_ready() -> None:
    if not state.pipeline or not state.pipeline.model_loaded:
        raise_api_error("model_not_ready", "Model not loaded", 503)


def raise_api_error(code: str, message: str, status: int) -> None:
    raise HTTPException(status_code=status, detail={"error": code, "message": message})


def main() -> None:
    parser = argparse.ArgumentParser(description="hailo-florence service")
    parser.add_argument(
        "--config",
        default=_config_path(),
        help="Path to JSON config (default: XDG config)",
    )
    parser.add_argument("--host", default=None, help="Override host")
    parser.add_argument("--port", type=int, default=None, help="Override port")

    args = parser.parse_args()

    if args.config:
        os.environ["FLORENCE_CONFIG"] = args.config

    config = FlorenceConfig.load()
    host = args.host or config.server_host
    port = args.port or config.server_port

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=config.log_level)


if __name__ == "__main__":
    main()
