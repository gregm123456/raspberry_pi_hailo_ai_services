#!/usr/bin/env python3
"""YamNet audio event classification service for Hailo-10H."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
from aiohttp import web

try:
    from device_client import HailoDeviceClient
except ImportError as exc:
    raise RuntimeError("device_client.py must be available on PYTHONPATH") from exc

logger = logging.getLogger("hailo-audio")
SAMPLE_RATE = 16000
WINDOW_LENGTH = 400
HOP_LENGTH = 160
FFT_LENGTH = 512
MEL_BANDS = 64
MEL_MIN_HZ = 125.0
MEL_MAX_HZ = 7500.0
LOG_OFFSET = 0.001
PATCH_FRAMES = 96
PATCH_HOP = 48
MAX_AUDIO_SECONDS = 60
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MODEL_PATH = os.environ.get(
    "HAILO_AUDIO_MODEL", "/var/lib/hailo-audio/resources/models/hailo10h/yamnet.hef"
)
CLASS_MAP_PATH = os.environ.get(
    "HAILO_AUDIO_CLASS_MAP", "/var/lib/hailo-audio/resources/yamnet_class_map.json"
)


def decode_pcm_wav(data: bytes, max_seconds: int = MAX_AUDIO_SECONDS) -> tuple[np.ndarray, float]:
    """Decode an uncompressed PCM WAV, downmixing and resampling to 16 kHz."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise ValueError("Only uncompressed PCM WAV files are supported")
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            frame_count = wav.getnframes()
            if channels < 1 or channels > 8 or sample_rate < 1:
                raise ValueError("Invalid WAV channel count or sample rate")
            duration = frame_count / sample_rate
            if duration <= 0 or duration > max_seconds:
                raise ValueError(f"Audio duration must be between 0 and {max_seconds} seconds")
            raw = wav.readframes(frame_count)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid WAV file: {exc}") from exc

    if sample_width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        triplets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        pcm = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
        pcm = (pcm ^ 0x800000) - 0x800000
        samples = pcm.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes")

    if samples.size != frame_count * channels:
        raise ValueError("WAV data is truncated")
    samples = samples.reshape(frame_count, channels).mean(axis=1)
    if sample_rate != SAMPLE_RATE:
        target_count = max(1, round(frame_count * SAMPLE_RATE / sample_rate))
        source_times = np.arange(frame_count, dtype=np.float64) / sample_rate
        target_times = np.arange(target_count, dtype=np.float64) / SAMPLE_RATE
        samples = np.interp(target_times, source_times, samples).astype(np.float32)
    return samples.astype(np.float32), duration


def _mel_weight_matrix() -> np.ndarray:
    """Build TensorFlow's HTK mel triangular filter bank for YamNet."""
    frequencies = np.arange(FFT_LENGTH // 2 + 1, dtype=np.float32) * SAMPLE_RATE / FFT_LENGTH
    def hz_to_mel(hz: np.ndarray | float) -> np.ndarray:
        return 1127.0 * np.log1p(np.asarray(hz) / 700.0)

    edges = np.linspace(hz_to_mel(MEL_MIN_HZ), hz_to_mel(MEL_MAX_HZ), MEL_BANDS + 2)
    mel = hz_to_mel(frequencies)[:, None]
    lower = (mel - edges[:-2]) / (edges[1:-1] - edges[:-2])
    upper = (edges[2:] - mel) / (edges[2:] - edges[1:-1])
    return np.maximum(0.0, np.minimum(lower, upper)).astype(np.float32)


_MEL_WEIGHTS = _mel_weight_matrix()


def waveform_to_log_mel_patches(waveform: np.ndarray) -> np.ndarray:
    """Convert mono 16 kHz audio to YamNet's (patch, 96, 64, 1) inputs."""
    waveform = np.asarray(waveform, dtype=np.float32).reshape(-1)
    if waveform.size == 0:
        raise ValueError("Audio contains no samples")
    minimum_samples = (PATCH_FRAMES - 1) * HOP_LENGTH + WINDOW_LENGTH
    if waveform.size < minimum_samples:
        waveform = np.pad(waveform, (0, minimum_samples - waveform.size))
    frame_count = 1 + (waveform.size - WINDOW_LENGTH) // HOP_LENGTH
    starts = np.arange(frame_count) * HOP_LENGTH
    frames = np.stack([waveform[s:s + WINDOW_LENGTH] for s in starts])
    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(WINDOW_LENGTH) / WINDOW_LENGTH)
    magnitude = np.abs(np.fft.rfft(frames * window, n=FFT_LENGTH, axis=1)).astype(np.float32)
    log_mel = np.log(magnitude @ _MEL_WEIGHTS + LOG_OFFSET).astype(np.float32)
    starts = range(0, frame_count - PATCH_FRAMES + 1, PATCH_HOP)
    patches = np.stack([log_mel[s:s + PATCH_FRAMES] for s in starts])
    return patches[..., np.newaxis].astype(np.float32)


def decode_tensor(payload: dict[str, Any]) -> np.ndarray:
    raw = base64.b64decode(payload["data_b64"], validate=True)
    array = np.frombuffer(raw, dtype=np.dtype(payload["dtype"]))
    return array.reshape(payload["shape"]).copy()


class YamNetService:
    def __init__(self) -> None:
        self.client: HailoDeviceClient | None = None
        self.labels: list[str] = []
        self.is_loaded = False

    async def initialize(self) -> None:
        model_path = Path(MODEL_PATH)
        labels_path = Path(CLASS_MAP_PATH)
        if not model_path.is_file():
            raise FileNotFoundError(f"YamNet HEF not found: {model_path}")
        if not labels_path.is_file():
            raise FileNotFoundError(f"YamNet class map not found: {labels_path}")
        class_map = json.loads(labels_path.read_text(encoding="utf-8"))
        self.labels = [class_map[str(i)]["display_name"] for i in range(521)]
        if len(self.labels) != 521:
            raise ValueError(f"Expected 521 YamNet labels, got {len(self.labels)}")
        self.client = HailoDeviceClient(timeout=60)
        await self.client.connect()
        await self.client.load_model(str(model_path), model_type="audio_classification")
        self.is_loaded = True
        logger.info("YamNet ready: %s", model_path)

    async def classify(self, audio: bytes, top_k: int = 5) -> dict[str, Any]:
        if not self.is_loaded or self.client is None:
            raise RuntimeError("YamNet model is not loaded")
        waveform, duration = decode_pcm_wav(audio)
        patches = waveform_to_log_mel_patches(waveform)
        scores = []
        started = time.monotonic()
        for patch in patches:
            response = await self.client.infer(
                MODEL_PATH,
                {"input": {"dtype": "float32", "shape": list(patch.shape),
                           "data_b64": base64.b64encode(patch.tobytes()).decode("ascii")}},
                model_type="audio_classification",
            )
            logits = decode_tensor(response["result"]).reshape(-1)
            if logits.size != 521:
                raise RuntimeError(f"YamNet returned {logits.size} scores, expected 521")
            scores.append(1.0 / (1.0 + np.exp(-np.clip(logits, -80.0, 80.0))))
        mean_scores = np.mean(scores, axis=0)
        indices = np.argsort(mean_scores)[-top_k:][::-1]
        return {
            "model": "yamnet",
            "duration_seconds": round(duration, 3),
            "patch_count": int(len(patches)),
            "inference_time_ms": round((time.monotonic() - started) * 1000, 2),
            "predictions": [
                {"class_id": int(i), "label": self.labels[int(i)], "score": float(mean_scores[i])}
                for i in indices
            ],
        }

    async def close(self) -> None:
        if self.client is not None:
            await self.client.disconnect()
            self.client = None
        self.is_loaded = False


service = YamNetService()


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "hailo-audio", "model_loaded": service.is_loaded})


async def readiness(_: web.Request) -> web.Response:
    if not service.is_loaded:
        return web.json_response({"status": "not_ready"}, status=503)
    return web.json_response({"status": "ready", "model": "yamnet"})


async def classify(request: web.Request) -> web.Response:
    reader = await request.multipart()
    field = await reader.next()
    while field is not None and field.name != "file":
        field = await reader.next()
    if field is None:
        raise web.HTTPBadRequest(text="multipart field 'file' is required")
    content = await field.read(decode=False)
    if len(content) > MAX_UPLOAD_BYTES:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_UPLOAD_BYTES, actual_size=len(content))
    try:
        top_k = int(request.query.get("top_k", "5"))
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        result = await service.classify(content, top_k)
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc)) from exc
    return web.json_response(result)


async def on_startup(app: web.Application) -> None:
    await service.initialize()


async def on_cleanup(app: web.Application) -> None:
    await service.close()


def create_app() -> web.Application:
    app = web.Application(client_max_size=MAX_UPLOAD_BYTES)
    app.router.add_get("/health", health)
    app.router.add_get("/ready", readiness)
    app.router.add_post("/v1/classify", classify)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    web.run_app(create_app(), host="0.0.0.0", port=int(os.environ.get("HAILO_AUDIO_PORT", "11441")))
