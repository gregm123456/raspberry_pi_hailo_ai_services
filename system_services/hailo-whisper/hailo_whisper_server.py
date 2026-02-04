#!/usr/bin/env python3
"""Hailo Whisper Service - Speech-to-Text on Hailo-10H."""

import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from aiohttp import web

from hailo_platform import VDevice
from hailo_platform.genai import Speech2Text, Speech2TextTask

from hailo_apps.python.core.common.core import resolve_hef_path
from hailo_apps.python.core.common.defines import HAILO10H_ARCH, WHISPER_CHAT_APP


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("hailo-whisper")


XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", "/etc/xdg")
CONFIG_JSON = os.path.join(XDG_CONFIG_HOME, "hailo-whisper", "hailo-whisper.json")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
TARGET_SAMPLE_RATE = 16000


@dataclass
class WhisperServiceConfig:
    server_host: str = "0.0.0.0"
    server_port: int = 11437
    model_name: str = "Whisper-Base"
    model_variant: str = "base"
    keep_alive: int = -1
    language: Optional[str] = "en"
    temperature: float = 0.0
    beam_size: int = 5
    vad_filter: bool = True
    max_audio_duration_seconds: int = 300
    cache_dir: str = "/var/lib/hailo-whisper/cache"
    resources_dir: str = "/var/lib/hailo-whisper/resources"

    @classmethod
    def load(cls) -> "WhisperServiceConfig":
        if not os.path.exists(CONFIG_JSON):
            logger.warning("Config not found at %s, using defaults", CONFIG_JSON)
            return cls()

        with open(CONFIG_JSON, "r", encoding="utf-8") as handle:
            config = json.load(handle) or {}

        server = config.get("server", {})
        model = config.get("model", {})
        transcription = config.get("transcription", {})
        storage = config.get("storage", {})

        return cls(
            server_host=server.get("host", "0.0.0.0"),
            server_port=int(server.get("port", 11437)),
            model_name=model.get("name", "Whisper-Base"),
            model_variant=model.get("variant", "base"),
            keep_alive=int(model.get("keep_alive", -1)),
            language=transcription.get("language", "en"),
            temperature=float(transcription.get("temperature", 0.0)),
            beam_size=int(transcription.get("beam_size", 5)),
            vad_filter=bool(transcription.get("vad_filter", True)),
            max_audio_duration_seconds=int(
                transcription.get("max_audio_duration_seconds", 300)
            ),
            cache_dir=storage.get("cache_dir", "/var/lib/hailo-whisper/cache"),
            resources_dir=storage.get("resources_dir", "/var/lib/hailo-whisper/resources"),
        )


class WhisperModelManager:
    def __init__(self, config: WhisperServiceConfig) -> None:
        self.config = config
        self._vdevice: Optional[VDevice] = None
        self._speech2text: Optional[Speech2Text] = None
        self._loaded_at = 0.0
        self._last_used = 0.0
        self._lock = asyncio.Lock()
        self._infer_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._speech2text is not None

    async def load(self) -> None:
        async with self._lock:
            if self._speech2text is not None:
                return

            logger.info("Loading Whisper model: %s", self.config.model_name)
            hef_path = resolve_hef_path(
                self.config.model_name or None,
                app_name=WHISPER_CHAT_APP,
                arch=HAILO10H_ARCH,
            )
            if hef_path is None:
                raise RuntimeError(
                    "Whisper HEF not found. Run install.sh to download resources."
                )

            params = VDevice.create_params()
            self._vdevice = VDevice(params)
            self._speech2text = Speech2Text(self._vdevice, str(hef_path))
            self._loaded_at = time.time()
            self._last_used = self._loaded_at
            logger.info("Whisper model loaded from %s", hef_path)

    async def unload(self) -> None:
        async with self._lock:
            if self._speech2text is not None:
                try:
                    self._speech2text.release()
                except Exception:
                    logger.warning("Failed to release Speech2Text", exc_info=True)
            if self._vdevice is not None:
                try:
                    self._vdevice.release()
                except Exception:
                    logger.warning("Failed to release VDevice", exc_info=True)

            self._speech2text = None
            self._vdevice = None
            self._loaded_at = 0.0
            self._last_used = 0.0
            logger.info("Whisper model unloaded")

    async def transcribe(self, audio_data: np.ndarray, language: str) -> List[Any]:
        if not self.is_loaded:
            await self.load()

        assert self._speech2text is not None
        async with self._infer_lock:
            self._last_used = time.time()
            return self._speech2text.generate_all_segments(
                audio_data=audio_data,
                task=Speech2TextTask.TRANSCRIBE,
                language=language,
                timeout_ms=15000,
            )

    async def maybe_unload_after_request(self) -> None:
        if self.config.keep_alive == 0:
            await self.unload()

    async def idle_unload_loop(self) -> None:
        if self.config.keep_alive <= 0:
            return

        while True:
            await asyncio.sleep(5)
            if not self.is_loaded:
                continue

            idle_for = time.time() - self._last_used
            if idle_for >= self.config.keep_alive:
                await self.unload()


class WhisperService:
    def __init__(self, config: WhisperServiceConfig) -> None:
        self.config = config
        self.model = WhisperModelManager(config)
        self.startup_time = datetime.utcnow()
        self.transcription_count = 0
        self._idle_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        os.makedirs(self.config.cache_dir, exist_ok=True)
        await self.model.load()

        if self.config.keep_alive > 0:
            self._idle_task = asyncio.create_task(self.model.idle_unload_loop())

    async def shutdown(self) -> None:
        if self._idle_task:
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        await self.model.unload()

    def _save_upload(self, data: bytes, mime_type: str) -> Path:
        ext = mimetypes.guess_extension(mime_type) or ".bin"
        if ext == ".bin":
            if "audio/mpeg" in mime_type or "audio/mp3" in mime_type:
                ext = ".mp3"
            elif "audio/wav" in mime_type or "audio/wave" in mime_type:
                ext = ".wav"
            elif "audio/ogg" in mime_type:
                ext = ".ogg"
            elif "audio/flac" in mime_type:
                ext = ".flac"
            elif "audio/webm" in mime_type:
                ext = ".webm"

        tmp_file = tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=ext,
            dir=self.config.cache_dir,
            delete=False,
        )
        tmp_file.write(data)
        tmp_file.close()
        return Path(tmp_file.name)

    def _decode_audio(self, audio_file: Path) -> Tuple[np.ndarray, float]:
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio_file),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-",
        ]

        result = subprocess.run(cmd, check=False, capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg failed: {stderr}")

        audio = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)
        if audio.size == 0:
            raise RuntimeError("Decoded audio was empty")

        audio = (audio / 32768.0).astype("<f4")
        duration = float(audio.size) / float(TARGET_SAMPLE_RATE)
        return audio, duration

    def _apply_vad(self, audio: np.ndarray) -> np.ndarray:
        if not self.config.vad_filter:
            return audio

        energy = np.abs(audio)
        threshold = 0.02
        indices = np.where(energy > threshold)[0]
        if indices.size == 0:
            return audio

        start = max(indices[0] - TARGET_SAMPLE_RATE // 10, 0)
        end = min(indices[-1] + TARGET_SAMPLE_RATE // 10, audio.size)
        return audio[start:end]

    async def transcribe(
        self,
        audio_data: bytes,
        mime_type: str,
        language: Optional[str],
    ) -> Dict[str, Any]:
        audio_file = self._save_upload(audio_data, mime_type)
        try:
            audio, duration = self._decode_audio(audio_file)
            if duration > self.config.max_audio_duration_seconds:
                raise ValueError(
                    f"Audio duration exceeds {self.config.max_audio_duration_seconds} seconds"
                )

            audio = self._apply_vad(audio)
            resolved_language = language if language not in (None, "") else self.config.language
            if resolved_language in (None, "", "null"):
                resolved_language = "auto"

            start_time = time.time()
            segments = await self.model.transcribe(audio, resolved_language)
            inference_ms = int((time.time() - start_time) * 1000)

            segment_payloads = []
            for idx, segment in enumerate(segments or []):
                start_sec = getattr(segment, "start_sec", 0.0)
                end_sec = getattr(segment, "end_sec", 0.0)
                text = getattr(segment, "text", "")
                segment_payloads.append(
                    {
                        "id": idx,
                        "start": float(start_sec),
                        "end": float(end_sec),
                        "text": text,
                        "tokens": [],
                        "temperature": self.config.temperature,
                        "avg_logprob": None,
                        "compression_ratio": None,
                        "no_speech_prob": None,
                    }
                )

            full_text = "".join([seg.get("text", "") for seg in segment_payloads]).strip()

            self.transcription_count += 1
            return {
                "text": full_text,
                "segments": segment_payloads,
                "language": resolved_language,
                "duration": duration,
                "inference_time_ms": inference_ms,
            }
        finally:
            if audio_file.exists():
                try:
                    audio_file.unlink()
                except Exception:
                    logger.warning("Failed to delete temp file %s", audio_file)


class APIHandler:
    def __init__(self, service: WhisperService) -> None:
        self.service = service

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "model": self.service.config.model_name,
                "model_loaded": self.service.model.is_loaded,
                "uptime_seconds": (datetime.utcnow() - self.service.startup_time).total_seconds(),
                "transcriptions_processed": self.service.transcription_count,
            }
        )

    async def health_ready(self, request: web.Request) -> web.Response:
        if self.service.model.is_loaded:
            return web.json_response({"ready": True})
        return web.json_response({"ready": False, "reason": "model_loading"}, status=503)

    async def list_models(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "data": [
                    {
                        "id": self.service.config.model_name,
                        "object": "model",
                        "created": int(self.service.startup_time.timestamp()),
                        "owned_by": "hailo",
                    }
                ],
                "object": "list",
            }
        )

    async def transcriptions(self, request: web.Request) -> web.Response:
        # Enforce multipart/form-data content type for OpenAI Whisper API compatibility
        content_type = request.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return self._error_response(
                "Content-Type must be multipart/form-data. "
                "This endpoint follows the OpenAI Whisper API specification and requires "
                "audio files to be uploaded as multipart form data with a 'file' field. "
                "Raw audio payloads are not supported.",
                status=415,
                error_type="invalid_request_error",
            )

        try:
            reader = await request.multipart()
        except Exception as exc:
            return self._error_response(
                f"Invalid multipart request: {exc}",
                status=400,
                error_type="invalid_request_error",
            )

        audio_data = None
        audio_mime = "application/octet-stream"
        model = None
        language = None
        response_format = "json"
        prompt = None
        temperature = None

        async for field in reader:
            if field.name == "file":
                audio_data = await field.read()
                audio_mime = field.headers.get("Content-Type", audio_mime)
            elif field.name == "model":
                model = (await field.read()).decode("utf-8", errors="ignore").strip()
            elif field.name == "language":
                language = (await field.read()).decode("utf-8", errors="ignore").strip() or None
            elif field.name == "response_format":
                response_format = (
                    await field.read()
                ).decode("utf-8", errors="ignore").strip()
            elif field.name == "prompt":
                prompt = (await field.read()).decode("utf-8", errors="ignore").strip() or None
            elif field.name == "temperature":
                try:
                    temp_str = (await field.read()).decode("utf-8", errors="ignore").strip()
                    if temp_str:
                        temperature = float(temp_str)
                except (ValueError, AttributeError):
                    pass  # Keep as None if invalid

        if not audio_data:
            return self._error_response("Missing 'file' field", status=400)

        if not model:
            return self._error_response("Missing 'model' field", status=400)

        if model != self.service.config.model_name:
            return self._error_response(
                f"Unsupported model '{model}'. Available: {self.service.config.model_name}",
                status=400,
            )

        if len(audio_data) > MAX_UPLOAD_BYTES:
            return self._error_response(
                f"Audio file too large (max {MAX_UPLOAD_BYTES} bytes)", status=400
            )

        try:
            result = await self.service.transcribe(audio_data, audio_mime, language)
            await self.service.model.maybe_unload_after_request()
        except ValueError as exc:
            return self._error_response(str(exc), status=400)
        except Exception as exc:
            logger.error("Transcription error: %s", exc, exc_info=True)
            return self._error_response(str(exc), status=500, error_type="internal_error")

        if response_format == "json":
            return web.json_response({"text": result["text"]})
        if response_format == "verbose_json":
            return web.json_response(
                {
                    "task": "transcribe",
                    "language": result["language"],
                    "duration": result["duration"],
                    "text": result["text"],
                    "segments": result["segments"],
                }
            )
        if response_format == "text":
            return web.Response(text=result["text"], content_type="text/plain")
        if response_format == "srt":
            return web.Response(
                text=self._format_srt(result["segments"]),
                content_type="text/plain",
            )
        if response_format == "vtt":
            return web.Response(
                text=self._format_vtt(result["segments"]),
                content_type="text/vtt",
            )

        return web.json_response({"text": result["text"]})

    def _format_srt(self, segments: List[Dict[str, Any]]) -> str:
        lines = []
        for idx, segment in enumerate(segments, 1):
            start = self._format_timestamp(segment.get("start", 0.0), srt=True)
            end = self._format_timestamp(segment.get("end", 0.0), srt=True)
            text = segment.get("text", "").strip()
            lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _format_vtt(self, segments: List[Dict[str, Any]]) -> str:
        lines = ["WEBVTT\n"]
        for segment in segments:
            start = self._format_timestamp(segment.get("start", 0.0), srt=False)
            end = self._format_timestamp(segment.get("end", 0.0), srt=False)
            text = segment.get("text", "").strip()
            lines.append(f"{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _format_timestamp(self, seconds: float, srt: bool = True) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        if srt:
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def _error_response(
        self, message: str, status: int = 400, error_type: str = "invalid_request_error"
    ) -> web.Response:
        return web.json_response(
            {"error": {"message": message, "type": error_type}},
            status=status,
        )


async def create_app(service: WhisperService) -> web.Application:
    handler = APIHandler(service)
    app = web.Application(client_max_size=MAX_UPLOAD_BYTES + 1024 * 1024)

    app.router.add_get("/health", handler.health)
    app.router.add_get("/health/ready", handler.health_ready)
    app.router.add_get("/v1/models", handler.list_models)
    app.router.add_post("/v1/audio/transcriptions", handler.transcriptions)

    return app


async def main() -> None:
    config = WhisperServiceConfig.load()
    logger.info("Hailo Whisper Service starting")
    logger.info("Server: %s:%s", config.server_host, config.server_port)
    logger.info("Model: %s", config.model_name)

    service = WhisperService(config)

    try:
        await service.initialize()

        app = await create_app(service)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.server_host, config.server_port)
        await site.start()

        logger.info(
            "Service ready at http://%s:%s", config.server_host, config.server_port
        )

        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
