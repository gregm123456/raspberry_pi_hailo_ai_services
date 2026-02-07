#!/usr/bin/env python3
"""
Hailo Device Manager - Exclusive Device Access & Request Serialization

This daemon owns the single Hailo-10H device context and serializes all
model loads and inferences across services via a Unix socket API.

Architecture:
- Holds exclusive VDevice connection
- Length-prefixed JSON protocol over Unix socket
- Single-threaded executor to serialize device operations
- Model handler registry for extensible inference types
"""

from __future__ import annotations

import asyncio
import base64
import grp
import http.server
import json
import logging
import logging.handlers
import os
import signal
import struct
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

import numpy as np

logger = logging.getLogger("hailo-device-manager")


def setup_logging() -> None:
    handlers = [logging.StreamHandler(sys.stdout)]
    if os.path.exists("/dev/log"):
        handlers.append(
            logging.handlers.SysLogHandler(
                address="/dev/log",
                facility=logging.handlers.SysLogHandler.LOG_DAEMON,
            )
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers,
    )


try:
    import hailo_platform
    from hailo_platform import FormatType
    from hailo_platform.genai import VLM, Speech2Text, Speech2TextTask
except ImportError as e:
    setup_logging()
    logger.error("Missing dependency: %s", e)
    logger.error("Install with: sudo apt install python3-h10-hailort")
    sys.exit(1)

try:
    from hailo_apps.python.core.common.defines import SHARED_VDEVICE_GROUP_ID
except ImportError:
    SHARED_VDEVICE_GROUP_ID = None


DEFAULT_SOCKET_PATH = "/run/hailo/device.sock"
DEFAULT_SOCKET_MODE = 0o660
DEFAULT_MAX_MESSAGE_BYTES = 64 * 1024 * 1024


def _get_env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value, 0)
    except ValueError:
        return default


def _get_env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _parse_http_bind(value: Optional[str]) -> Optional[tuple[str, int]]:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"0", "off", "false", "none", "disable", "disabled"}:
        return None
    if ":" in value:
        host, port_str = value.rsplit(":", 1)
        host = host.strip()
    else:
        host = "127.0.0.1"
        port_str = value
    try:
        port = int(port_str)
    except ValueError:
        return None
    if not host:
        host = "127.0.0.1"
    return host, port


async def _read_exact(reader: asyncio.StreamReader, size: int) -> Optional[bytes]:
    try:
        return await reader.readexactly(size)
    except asyncio.IncompleteReadError:
        return None


async def read_message(
    reader: asyncio.StreamReader, max_bytes: int
) -> Optional[Dict[str, Any]]:
    header = await _read_exact(reader, 4)
    if not header:
        return None
    (length,) = struct.unpack(">I", header)
    if length > max_bytes:
        raise ValueError(f"Message too large: {length} bytes")
    payload = await _read_exact(reader, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


async def write_message(
    writer: asyncio.StreamWriter, payload: Dict[str, Any], max_bytes: int
) -> None:
    body = json.dumps(payload).encode("utf-8")
    if len(body) > max_bytes:
        raise ValueError(f"Response too large: {len(body)} bytes")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()


@dataclass
class ModelEntry:
    model_type: str
    model_path: str
    model: Any
    loaded_at: float
    last_used: float


class ModelHandler:
    model_type = "vlm"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        raise NotImplementedError

    def infer(self, model: Any, input_data: Any) -> Any:
        raise NotImplementedError

    def unload(self, model: Any) -> None:
        if hasattr(model, "release"):
            model.release()


class VlmHandler(ModelHandler):
    model_type = "vlm"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        return VLM(vdevice, model_path)

    def infer(self, model: Any, input_data: Any) -> Any:
        return model.infer(input_data)


class VlmChatHandler(ModelHandler):
    model_type = "vlm_chat"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        return VLM(vdevice, model_path)

    def infer(self, model: Any, input_data: Any) -> Any:
        prompt = input_data.get("prompt")
        frames = input_data.get("frames", [])
        temperature = input_data.get("temperature")
        seed = input_data.get("seed")
        max_generated_tokens = input_data.get("max_generated_tokens")

        if not prompt or not frames:
            raise ValueError("prompt and frames are required for vlm_chat")

        decoded_frames = [decode_tensor(frame) for frame in frames]
        try:
            return model.generate_all(
                prompt=prompt,
                frames=decoded_frames,
                temperature=temperature,
                seed=seed,
                max_generated_tokens=max_generated_tokens,
            )
        finally:
            model.clear_context()


@dataclass
class ClipRuntime:
    image_infer_model: Any
    image_configured_model: Any
    text_infer_model: Any
    text_configured_model: Any
    text_input_layer: str
    text_output_layer: str


class WhisperHandler(ModelHandler):
    model_type = "whisper"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        return Speech2Text(vdevice, model_path)

    def infer(self, model: Any, input_data: Any) -> Any:
        audio = input_data.get("audio")
        language = input_data.get("language", "en")
        task_str = input_data.get("task", "transcribe")

        if not audio:
            raise ValueError("audio data is required for whisper")

        # Convert list back to numpy array if needed
        if isinstance(audio, list):
            audio = np.array(audio, dtype=np.float32)

        # Map task string to Speech2TextTask enum
        task = Speech2TextTask.TRANSCRIBE if task_str == "transcribe" else Speech2TextTask.TRANSLATE

        # Generate transcription segments
        segments = model.generate_all_segments(
            audio_data=audio,
            task=task,
            language=language,
            timeout_ms=15000,
        )

        # Convert segments to dict format
        segment_list = []
        for idx, segment in enumerate(segments or []):
            segment_list.append(
                {
                    "id": idx,
                    "start": float(segment.start_sec),
                    "end": float(segment.end_sec),
                    "text": segment.text,
                }
            )

        return {"segments": segment_list}


@dataclass
class OcrRuntime:
    """Runtime state for OCR models (detection + recognition)."""
    detection_model: Any
    detection_configured: Any
    detection_input_shape: tuple
    recognition_models: Dict[str, Any]  # lang -> InferModel
    recognition_configured: Dict[str, Any]  # lang -> ConfiguredInferModel
    batch_sizes: Dict[str, int]  # lang -> batch_size


class OcrHandler(ModelHandler):
    model_type = "ocr"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        det_hef_path = model_params.get("detection_hef_path")
        rec_hefs = model_params.get("recognition_hefs", {})  # {lang: path}
        batch_sizes = model_params.get("batch_sizes", {})

        if not det_hef_path:
            raise ValueError("detection_hef_path is required for ocr")
        if not rec_hefs:
            raise ValueError("recognition_hefs dict is required for ocr")

        if not Path(det_hef_path).exists():
            raise ValueError(f"Detection HEF not found: {det_hef_path}")

        # Load detection model
        logger.info("Loading OCR detection model: %s", det_hef_path)
        detection_model = vdevice.create_infer_model(str(det_hef_path))
        detection_model.input().set_format_type(FormatType.UINT8)
        detection_model.output().set_format_type(FormatType.FLOAT32)
        detection_configured = detection_model.configure()
        detection_input_shape = tuple(detection_model.input().shape)

        # Load recognition models for each language
        recognition_models = {}
        recognition_configured = {}
        for lang, hef_path in rec_hefs.items():
            if not Path(hef_path).exists():
                raise ValueError(f"Recognition HEF for {lang} not found: {hef_path}")
            
            logger.info("Loading OCR recognition model for %s: %s", lang, hef_path)
            rec_model = vdevice.create_infer_model(str(hef_path))
            rec_model.input().set_format_type(FormatType.UINT8)
            rec_model.output().set_format_type(FormatType.FLOAT32)
            recognition_models[lang] = rec_model
            recognition_configured[lang] = rec_model.configure()

        return OcrRuntime(
            detection_model=detection_model,
            detection_configured=detection_configured,
            detection_input_shape=detection_input_shape,
            recognition_models=recognition_models,
            recognition_configured=recognition_configured,
            batch_sizes=batch_sizes,
        )

    def infer(self, model: OcrRuntime, input_data: Any) -> Any:
        mode = input_data.get("mode")
        
        if mode == "detection":
            # Single detection inference
            image_tensor = decode_tensor(input_data.get("image"))
            
            bindings = model.detection_configured.create_bindings()
            
            # Set input buffer
            input_buffer = np.empty(model.detection_model.input().shape, dtype=np.uint8)
            input_buffer[:] = image_tensor
            bindings.input().set_buffer(input_buffer)
            
            # Set output buffer
            output_buffer = np.empty(model.detection_model.output().shape, dtype=np.float32)
            bindings.output().set_buffer(output_buffer)
            
            # Run inference
            model.detection_configured.wait_for_async_ready(timeout_ms=1000)
            job = model.detection_configured.run_async([bindings])
            job.wait(timeout_ms=1000)
            
            return encode_tensor(output_buffer.copy())

        elif mode == "recognition":
            # Batched recognition inference
            lang = input_data.get("language", "en")
            crops = input_data.get("crops", [])
            batch_size = input_data.get("batch_size", model.batch_sizes.get(lang, 8))

            if lang not in model.recognition_models:
                raise ValueError(f"Unsupported language: {lang}. Available: {list(model.recognition_models.keys())}")

            rec_model = model.recognition_models[lang]
            rec_configured = model.recognition_configured[lang]
            
            # Decode all crops
            decoded_crops = [decode_tensor(crop) for crop in crops]
            
            results = []
            # Process in batches
            for i in range(0, len(decoded_crops), batch_size):
                batch = decoded_crops[i:i + batch_size]
                actual_batch_size = len(batch)

                # Pad to batch_size if needed
                if actual_batch_size < batch_size:
                    padding_shape = batch[0].shape
                    padding = np.zeros(padding_shape, dtype=batch[0].dtype)
                    batch.extend([padding] * (batch_size - actual_batch_size))

                # Create bindings for each item in batch
                bindings_list = []
                output_buffers = []
                
                for j in range(batch_size):
                    bindings = rec_configured.create_bindings()
                    
                    # Set input buffer
                    input_buffer = np.empty(rec_model.input().shape, dtype=np.uint8)
                    input_buffer[:] = batch[j]
                    bindings.input().set_buffer(input_buffer)
                    
                    # Set output buffer
                    output_buffer = np.empty(rec_model.output().shape, dtype=np.float32)
                    bindings.output().set_buffer(output_buffer)
                    output_buffers.append(output_buffer)
                    
                    bindings_list.append(bindings)

                # Run batch inference
                rec_configured.wait_for_async_ready(timeout_ms=1000)
                job = rec_configured.run_async(bindings_list)
                job.wait(timeout_ms=1000)

                # Collect outputs, trim padding
                for j in range(actual_batch_size):
                    results.append(encode_tensor(output_buffers[j].copy()))

            return results

        else:
            raise ValueError(f"Unknown OCR mode: {mode}. Must be 'detection' or 'recognition'")

    def unload(self, model: OcrRuntime) -> None:
        # Release configured models and infer models
        for obj in [model.detection_configured, model.detection_model]:
            if hasattr(obj, "release"):
                obj.release()
        
        for configured in model.recognition_configured.values():
            if hasattr(configured, "release"):
                configured.release()
        
        for infer_model in model.recognition_models.values():
            if hasattr(infer_model, "release"):
                infer_model.release()


class ClipHandler(ModelHandler):
    model_type = "clip"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        image_hef_path = model_params.get("image_hef_path")
        text_hef_path = model_params.get("text_hef_path")
        text_input_layer = model_params.get("text_input_layer")
        text_output_layer = model_params.get("text_output_layer")

        if not image_hef_path or not text_hef_path:
            raise ValueError("image_hef_path and text_hef_path are required for clip")
        if not text_input_layer or not text_output_layer:
            raise ValueError("text_input_layer and text_output_layer are required for clip")

        if not Path(image_hef_path).exists():
            raise ValueError(f"Image HEF not found: {image_hef_path}")
        if not Path(text_hef_path).exists():
            raise ValueError(f"Text HEF not found: {text_hef_path}")

        image_infer_model = vdevice.create_infer_model(str(image_hef_path))
        image_infer_model.input().set_format_type(FormatType.UINT8)
        image_infer_model.output().set_format_type(FormatType.FLOAT32)
        image_configured_model = image_infer_model.configure()

        text_infer_model = vdevice.create_infer_model(str(text_hef_path))
        text_infer_model.input(text_input_layer).set_format_type(FormatType.FLOAT32)
        text_infer_model.output(text_output_layer).set_format_type(FormatType.FLOAT32)
        text_configured_model = text_infer_model.configure()

        return ClipRuntime(
            image_infer_model=image_infer_model,
            image_configured_model=image_configured_model,
            text_infer_model=text_infer_model,
            text_configured_model=text_configured_model,
            text_input_layer=text_input_layer,
            text_output_layer=text_output_layer,
        )

    def infer(self, model: ClipRuntime, input_data: Any) -> Any:
        mode = input_data.get("mode")
        tensor = input_data.get("tensor")
        timeout_ms = int(input_data.get("timeout_ms", 1000))

        if mode not in {"image", "text"}:
            raise ValueError("clip mode must be 'image' or 'text'")
        if not tensor:
            raise ValueError("tensor is required for clip inference")

        if mode == "image":
            input_array = decode_tensor(tensor)
            bindings = model.image_configured_model.create_bindings()

            input_buffer = np.empty(model.image_infer_model.input().shape, dtype=np.uint8)
            input_buffer[:] = input_array
            bindings.input().set_buffer(input_buffer)

            output_buffer = np.empty(model.image_infer_model.output().shape, dtype=np.float32)
            bindings.output().set_buffer(output_buffer)

            model.image_configured_model.run([bindings], timeout_ms)
            return encode_tensor(output_buffer)

        input_array = decode_tensor(tensor)
        bindings = model.text_configured_model.create_bindings()

        input_buffer = np.empty(
            model.text_infer_model.input(model.text_input_layer).shape,
            dtype=np.float32,
        )
        input_buffer[:] = input_array
        bindings.input(model.text_input_layer).set_buffer(input_buffer)

        output_buffer = np.empty(
            model.text_infer_model.output(model.text_output_layer).shape,
            dtype=np.float32,
        )
        bindings.output(model.text_output_layer).set_buffer(output_buffer)

        model.text_configured_model.run([bindings], timeout_ms)
        return encode_tensor(output_buffer)

    def unload(self, model: ClipRuntime) -> None:
        for obj in (
            model.image_configured_model,
            model.image_infer_model,
            model.text_configured_model,
            model.text_infer_model,
        ):
            if hasattr(obj, "release"):
                obj.release()


@dataclass
class DepthRuntime:
    """Runtime state for depth estimation model."""
    infer_model: Any
    configured_model: Any
    input_shape: tuple


class DepthHandler(ModelHandler):
    model_type = "depth"

    def load(
        self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]
    ) -> Any:
        """Load a monocular depth estimation model (e.g., scdepthv3)."""
        if not Path(model_path).exists():
            raise ValueError(f"Model HEF not found: {model_path}")

        logger.info("Loading depth model: %s", model_path)
        infer_model = vdevice.create_infer_model(str(model_path))
        infer_model.input().set_format_type(FormatType.UINT8)
        infer_model.output().set_format_type(FormatType.FLOAT32)
        configured_model = infer_model.configure()
        input_shape = tuple(infer_model.input().shape)

        return DepthRuntime(
            infer_model=infer_model,
            configured_model=configured_model,
            input_shape=input_shape,
        )

    def infer(self, model: DepthRuntime, input_data: Any) -> Any:
        """Run depth estimation inference."""
        input_tensor = decode_tensor(input_data.get("input"))

        bindings = model.configured_model.create_bindings()

        # Set input buffer
        input_buffer = np.empty(model.infer_model.input().shape, dtype=np.uint8)
        input_buffer[:] = input_tensor
        bindings.input().set_buffer(input_buffer)

        # Set output buffer
        output_buffer = np.empty(model.infer_model.output().shape, dtype=np.float32)
        bindings.output().set_buffer(output_buffer)

        # Run inference
        model.configured_model.wait_for_async_ready(timeout_ms=1000)
        job = model.configured_model.run_async([bindings])
        job.wait(timeout_ms=1000)

        return encode_tensor(output_buffer.copy())

    def unload(self, model: DepthRuntime) -> None:
        """Release depth model resources."""
        for obj in (model.configured_model, model.infer_model):
            if hasattr(obj, "release"):
                obj.release()


def encode_tensor(array: np.ndarray) -> Dict[str, Any]:
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }


def decode_tensor(payload: Dict[str, Any]) -> np.ndarray:
    dtype = payload.get("dtype")
    shape = payload.get("shape")
    data_b64 = payload.get("data_b64")

    if not dtype or shape is None or not data_b64:
        raise ValueError("tensor must include dtype, shape, and data_b64")

    raw = base64.b64decode(data_b64)
    array = np.frombuffer(raw, dtype=np.dtype(dtype))
    return array.reshape(shape).copy()  # Copy to make writeable


class HailoDeviceManager:
    """Manages exclusive access to Hailo device and serializes requests."""

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH) -> None:
        self.socket_path = socket_path
        self.device: Optional[hailo_platform.Device] = None
        self.vdevice: Optional[hailo_platform.VDevice] = None
        self.loaded_models: Dict[str, ModelEntry] = {}
        self.start_time = time.time()
        self.http_bind = _parse_http_bind(
            os.environ.get("HAILO_DEVICE_HTTP_BIND", "127.0.0.1:5099")
        )
        self.max_message_bytes = _get_env_int(
            "HAILO_DEVICE_MAX_MESSAGE_BYTES", DEFAULT_MAX_MESSAGE_BYTES
        )
        self.socket_mode = _get_env_int(
            "HAILO_DEVICE_SOCKET_MODE", DEFAULT_SOCKET_MODE
        )
        self.socket_group = os.environ.get("HAILO_DEVICE_SOCKET_GROUP")
        self._server: Optional[asyncio.AbstractServer] = None
        self._http_server: Optional[http.server.ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._handlers = {
            VlmHandler.model_type: VlmHandler(),
            VlmChatHandler.model_type: VlmChatHandler(),
            ClipHandler.model_type: ClipHandler(),
            WhisperHandler.model_type: WhisperHandler(),
            OcrHandler.model_type: OcrHandler(),
            DepthHandler.model_type: DepthHandler(),
        }
        self._queue_depth = 0

    async def initialize(self) -> None:
        logger.info("Initializing Hailo Device Manager...")

        try:
            devices = hailo_platform.Device.scan()
            if not devices:
                raise RuntimeError(
                    "No Hailo devices found. Install driver: sudo apt install dkms hailo-h10-all"
                )
            logger.info("Found %d device(s): %s", len(devices), devices)
        except Exception as e:
            raise RuntimeError(f"Failed to scan devices: {e}")

        try:
            self.device = hailo_platform.Device()
            logger.info("Opened device: %s", self.device.device_id)
        except Exception as e:
            raise RuntimeError(f"Failed to open device: {e}")

        try:
            params = hailo_platform.VDevice.create_params()
            group_id = _get_env_int("HAILO_DEVICE_GROUP_ID", -1)
            if group_id >= 0:
                params.group_id = group_id
            elif SHARED_VDEVICE_GROUP_ID is not None:
                params.group_id = SHARED_VDEVICE_GROUP_ID
            self.vdevice = hailo_platform.VDevice(params)
            logger.info("VDevice created successfully")
        except Exception as e:
            if self.device:
                self.device.release()
            raise RuntimeError(f"Failed to create VDevice: {e}")

        socket_dir = Path(self.socket_path).parent
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_dir.chmod(0o755)

        if Path(self.socket_path).exists():
            Path(self.socket_path).unlink()

        logger.info("Manager initialized. Socket: %s", self.socket_path)

    def _resolve_socket_group(self) -> Optional[int]:
        if self.socket_group:
            try:
                return grp.getgrnam(self.socket_group).gr_gid
            except KeyError:
                return None
        try:
            stat_info = os.stat("/dev/hailo0")
            return stat_info.st_gid
        except Exception:
            return None

    async def _worker_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            item = await self._request_queue.get()
            if item is None:
                self._request_queue.task_done()
                break
            request, future = item
            try:
                response = await loop.run_in_executor(
                    self._executor, self._handle_request_sync, request
                )
            except Exception as e:
                response = {"error": f"Internal error: {e}"}
            future.set_result(response)
            self._request_queue.task_done()
            self._queue_depth = max(0, self._queue_depth - 1)

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client_id = str(uuid.uuid4())[:8]
        try:
            while True:
                request = await read_message(reader, self.max_message_bytes)
                if request is None:
                    break

                response = await self.process_request(request)
                await write_message(writer, response, self.max_message_bytes)
        except ValueError as e:
            logger.warning("Client %s protocol error: %s", client_id, e)
            try:
                await write_message(
                    writer,
                    {"error": str(e)},
                    self.max_message_bytes,
                )
            except Exception:
                pass
        except json.JSONDecodeError as e:
            logger.warning("Client %s sent invalid JSON: %s", client_id, e)
        except Exception as e:
            logger.error("Error handling client %s: %s", client_id, e)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected while closing; safe to ignore.
                pass

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_id = request.get("request_id")
        response = await self._enqueue_request(request)
        if request_id is not None:
            response["request_id"] = request_id
        return response

    async def _enqueue_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self._request_queue.put((request, future))
        self._queue_depth += 1
        return await future

    def _handle_request_sync(self, request: Dict[str, Any]) -> Dict[str, Any]:
        action = request.get("action")
        if action == "ping":
            return self._status_payload(include_models=True)
        if action == "status":
            return self._status_payload(include_models=True)
        if action == "device_status":
            return self._device_status_payload()
        if action == "load_model":
            return self._load_model(request)
        if action == "infer":
            return self._infer(request)
        if action == "unload_model":
            return self._unload_model(request)
        return {"error": f"Unknown action: {action}"}

    def _status_payload(self, include_models: bool) -> Dict[str, Any]:
        models = []
        if include_models:
            for entry in self.loaded_models.values():
                models.append(
                    {
                        "model_type": entry.model_type,
                        "model_path": entry.model_path,
                        "loaded_at": entry.loaded_at,
                        "last_used": entry.last_used,
                    }
                )

        return {
            "status": "ok",
            "device_id": self.device.device_id if self.device else None,
            "loaded_models": models,
            "uptime_seconds": time.time() - self.start_time,
            "socket_path": self.socket_path,
            "queue_depth": self._queue_depth,
        }

    def _device_status_payload(self) -> Dict[str, Any]:
        if not self.device:
            return {"status": "error", "message": "Device not initialized"}

        device_info: Dict[str, Any] = {"device_id": self.device.device_id}
        try:
            board_info = self.device.control.identify()
            device_info.update(
                {
                    "architecture": str(board_info.device_architecture),
                    "fw_version": str(board_info.firmware_version),
                }
            )
        except Exception as e:
            device_info["identify_error"] = str(e)

        try:
            temp_info = self.device.control.get_chip_temperature()
            device_info["temperature_celsius"] = round(temp_info.ts0_temperature, 1)
        except Exception as e:
            device_info["temperature_celsius"] = None
            device_info["temperature_error"] = str(e)

        networks: Dict[str, Any] = {
            "status": "ok",
            "source": "device_manager",
            "network_count": len(self.loaded_models),
            "networks": [],
        }
        for entry in self.loaded_models.values():
            networks["networks"].append(
                {
                    "name": Path(entry.model_path).name,
                    "model_type": entry.model_type,
                    "model_path": entry.model_path,
                    "loaded_at": entry.loaded_at,
                    "last_used": entry.last_used,
                }
            )

        return {
            "status": "ok",
            "device": device_info,
            "networks": networks,
            "uptime_seconds": time.time() - self.start_time,
            "queue_depth": self._queue_depth,
        }

    def _start_http_server(self) -> None:
        if not self.http_bind:
            return

        host, port = self.http_bind
        manager = self

        class StatusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/v1/device/status":
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    body = json.dumps({"error": "Not found"}).encode("utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                payload = manager._device_status_payload()
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                logger.info("HTTP %s - %s", self.address_string(), format % args)

        try:
            self._http_server = http.server.ThreadingHTTPServer((host, port), StatusHandler)
        except OSError as exc:
            logger.error("Failed to start HTTP server on %s:%s: %s", host, port, exc)
            self._http_server = None
            return

        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            name="hailo-device-http",
            daemon=True,
        )
        self._http_thread.start()
        logger.info("HTTP status endpoint: http://%s:%s/v1/device/status", host, port)

    def _stop_http_server(self) -> None:
        if not self._http_server:
            return
        try:
            self._http_server.shutdown()
            self._http_server.server_close()
        except Exception as exc:
            logger.warning("Error stopping HTTP server: %s", exc)
        self._http_server = None
        if self._http_thread:
            self._http_thread.join(timeout=1.0)
            self._http_thread = None

    def _get_handler(self, model_type: str) -> ModelHandler:
        handler = self._handlers.get(model_type)
        if not handler:
            raise ValueError(f"Unsupported model_type: {model_type}")
        return handler

    def _model_key(self, model_type: str, model_path: str) -> str:
        return f"{model_type}:{model_path}"

    def _load_model(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_path = request.get("model_path")
        model_type = request.get("model_type", "vlm")
        model_params = request.get("model_params") or {}
        if not model_path:
            return {"error": "model_path required"}

        if not Path(model_path).exists():
            if model_type != "clip":
                return {"error": f"Model file not found: {model_path}"}

        key = self._model_key(model_type, model_path)
        if key in self.loaded_models:
            response = {
                "status": "ok",
                "model_path": model_path,
                "model_type": model_type,
                "message": "Model already loaded",
            }
            if model_type == "ocr":
                runtime = self.loaded_models[key].model
                response["model_info"] = {
                    "detection_input_shape": list(runtime.detection_input_shape),
                }
            return response

        try:
            handler = self._get_handler(model_type)
            logger.info("Loading model: %s (%s)", model_path, model_type)
            model = handler.load(self.vdevice, model_path, model_params)
            now = time.time()
            self.loaded_models[key] = ModelEntry(
                model_type=model_type,
                model_path=model_path,
                model=model,
                loaded_at=now,
                last_used=now,
            )
            response = {
                "status": "ok",
                "model_path": model_path,
                "model_type": model_type,
                "message": "Model loaded",
            }
            if model_type == "ocr":
                response["model_info"] = {
                    "detection_input_shape": list(model.detection_input_shape),
                }
            return response
        except Exception as e:
            logger.error("Failed to load model %s: %s", model_path, e)
            return {"error": f"Failed to load model: {e}"}

    def _infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_path = request.get("model_path")
        model_type = request.get("model_type", "vlm")
        input_data = request.get("input_data")
        if not model_path or input_data is None:
            return {"error": "model_path and input_data required"}

        try:
            key = self._model_key(model_type, model_path)
            if key not in self.loaded_models:
                load_result = self._load_model({
                    "model_path": model_path,
                    "model_type": model_type,
                    "model_params": request.get("model_params") or {},
                })
                if load_result.get("error"):
                    return load_result

            entry = self.loaded_models[key]
            handler = self._get_handler(model_type)
            logger.info("Running inference with %s (%s)", model_path, model_type)
            start_time = time.time()
            result = handler.infer(entry.model, input_data)
            inference_time_ms = int((time.time() - start_time) * 1000)
            entry.last_used = time.time()
            return {
                "status": "ok",
                "result": result,
                "inference_time_ms": inference_time_ms,
            }
        except Exception as e:
            logger.error("Inference failed: %s", e)
            return {"error": f"Inference failed: {e}"}

    def _unload_model(self, request: Dict[str, Any]) -> Dict[str, Any]:
        model_path = request.get("model_path")
        model_type = request.get("model_type", "vlm")
        if not model_path:
            return {"error": "model_path required"}

        key = self._model_key(model_type, model_path)
        entry = self.loaded_models.get(key)
        if not entry:
            return {"status": "ok", "message": "Model was not loaded"}

        try:
            handler = self._get_handler(model_type)
            handler.unload(entry.model)
            del self.loaded_models[key]
            logger.info("Model unloaded: %s (%s)", model_path, model_type)
            return {"status": "ok", "message": "Model unloaded"}
        except Exception as e:
            logger.error("Failed to unload model: %s", e)
            return {"error": str(e)}

    async def start_server(self) -> None:
        logger.info("Starting server on %s", self.socket_path)
        self._server = await asyncio.start_unix_server(
            self.handle_client, path=self.socket_path
        )

        socket_gid = self._resolve_socket_group()
        if socket_gid is not None:
            os.chown(self.socket_path, -1, socket_gid)
        os.chmod(self.socket_path, self.socket_mode)

        self._start_http_server()

        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Device manager ready for connections")

        async with self._server:
            await self._server.serve_forever()

    async def shutdown(self) -> None:
        logger.info("Shutting down...")

        self._stop_http_server()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        if self._worker_task:
            await self._request_queue.put(None)
            await self._worker_task

        for entry in list(self.loaded_models.values()):
            try:
                self._get_handler(entry.model_type).unload(entry.model)
            except Exception as e:
                logger.warning("Error during model cleanup: %s", e)
        self.loaded_models.clear()

        if self.vdevice:
            try:
                self.vdevice.release()
                logger.info("VDevice released")
            except Exception as e:
                logger.warning("Error releasing VDevice: %s", e)

        if self.device:
            try:
                self.device.release()
                logger.info("Device released")
            except Exception as e:
                logger.warning("Error releasing Device: %s", e)

        try:
            if Path(self.socket_path).exists():
                Path(self.socket_path).unlink()
                logger.info("Socket cleaned up: %s", self.socket_path)
        except Exception as e:
            logger.warning("Error cleaning socket: %s", e)

        self._executor.shutdown(wait=False)
        logger.info("Shutdown complete")


async def run() -> None:
    socket_path = _get_env_str("HAILO_DEVICE_SOCKET", DEFAULT_SOCKET_PATH)
    if len(sys.argv) > 1 and sys.argv[1] == "--socket-path" and len(sys.argv) > 2:
        socket_path = sys.argv[2]

    manager = HailoDeviceManager(socket_path)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_shutdown() -> None:
        if not stop_event.is_set():
            stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _request_shutdown())

    await manager.initialize()
    server_task = asyncio.create_task(manager.start_server())

    await stop_event.wait()
    await manager.shutdown()
    server_task.cancel()


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
