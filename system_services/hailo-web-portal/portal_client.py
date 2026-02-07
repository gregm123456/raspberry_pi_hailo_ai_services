from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=120)


def _encode_file_to_data_uri(path: str, default_mime: str = "image/jpeg") -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = default_mime
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _encode_file_base64(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("ascii")


def _guess_mime(path: str, default_mime: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or default_mime


async def _request_json(
    method: str,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[aiohttp.FormData] = None,
    timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, url, json=json_body, data=data) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                payload: Dict[str, Any] = await resp.json()
            else:
                payload = {"text": await resp.text()}

            if resp.status >= 400:
                return {"error": payload, "status": resp.status}
            return payload


async def _request_bytes(
    method: str,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[aiohttp.FormData] = None,
    timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
) -> bytes:
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, url, json=json_body, data=data) as resp:
            return await resp.read()


async def _request_text(
    method: str,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[aiohttp.FormData] = None,
    timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
) -> str:
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, url, json=json_body, data=data) as resp:
            return await resp.text()


class HailoClipClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5000") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def classify(
        self, image_path: str, prompts: List[str], top_k: int = 3, threshold: float = 0.0
    ) -> Dict[str, Any]:
        payload = {
            "image": _encode_file_to_data_uri(image_path),
            "prompts": prompts,
            "top_k": top_k,
            "threshold": threshold,
        }
        return await _request_json("POST", f"{self.base_url}/v1/classify", json_body=payload)

    async def embed_image(self, image_path: str) -> Dict[str, Any]:
        payload = {"image": _encode_file_to_data_uri(image_path)}
        return await _request_json("POST", f"{self.base_url}/v1/embed/image", json_body=payload)

    async def embed_text(self, text: str) -> Dict[str, Any]:
        payload = {"text": text}
        return await _request_json("POST", f"{self.base_url}/v1/embed/text", json_body=payload)


class HailoVisionClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11435") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def chat_completions(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 200,
        top_p: float = 0.9,
        stream: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": _encode_file_to_data_uri(image_path)}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
        }
        if stream:
            text = await _request_text(
                "POST", f"{self.base_url}/v1/chat/completions", json_body=payload
            )
            return {"stream": text}
        return await _request_json("POST", f"{self.base_url}/v1/chat/completions", json_body=payload)

    async def vision_analyze(
        self,
        image_paths: List[str],
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 150,
        return_individual_results: bool = False,
    ) -> Dict[str, Any]:
        images = [_encode_file_to_data_uri(path) for path in image_paths]
        payload = {
            "images": images,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "return_individual_results": return_individual_results,
        }
        return await _request_json("POST", f"{self.base_url}/v1/vision/analyze", json_body=payload)


class HailoWhisperClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11437") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def readiness(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health/ready")

    async def list_models(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/v1/models")

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        response_format: str = "json",
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        form_data = aiohttp.FormData()
        audio_bytes = Path(audio_path).read_bytes()
        form_data.add_field(
            "file",
            audio_bytes,
            filename=Path(audio_path).name,
            content_type=_guess_mime(audio_path, "audio/mpeg"),
        )
        form_data.add_field("model", "Whisper-Base")
        if language:
            form_data.add_field("language", language)
        form_data.add_field("response_format", response_format)
        form_data.add_field("temperature", str(temperature))

        if response_format in {"text", "srt", "vtt"}:
            text = await _request_text(
                "POST", f"{self.base_url}/v1/audio/transcriptions", data=form_data
            )
            return {"text": text}
        return await _request_json(
            "POST", f"{self.base_url}/v1/audio/transcriptions", data=form_data
        )


class HailoOCRClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11436") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def readiness(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health/ready")

    async def list_models(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/models")

    async def extract_text(self, image_path: str, languages: List[str]) -> Dict[str, Any]:
        payload = {"image": _encode_file_to_data_uri(image_path), "languages": languages}
        return await _request_json("POST", f"{self.base_url}/v1/ocr/extract", json_body=payload)


class HailoPoseClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11440") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def readiness(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health/ready")

    async def list_models(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/v1/models")

    async def detect_poses(
        self,
        image_path: str,
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        max_detections: int = 10,
        keypoint_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        form_data = aiohttp.FormData()
        image_bytes = Path(image_path).read_bytes()
        form_data.add_field(
            "image",
            image_bytes,
            filename=Path(image_path).name,
            content_type=_guess_mime(image_path, "image/jpeg"),
        )
        form_data.add_field("confidence_threshold", str(confidence_threshold))
        form_data.add_field("iou_threshold", str(iou_threshold))
        form_data.add_field("max_detections", str(max_detections))
        form_data.add_field("keypoint_threshold", str(keypoint_threshold))
        return await _request_json("POST", f"{self.base_url}/v1/pose/detect", data=form_data)


class HailoDepthClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11439") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def readiness(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health/ready")

    async def info(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/v1/info")

    async def estimate_depth(
        self,
        image_path: str,
        output_format: str = "both",
        normalize: bool = True,
        colormap: str = "viridis",
    ) -> Dict[str, Any]:
        form_data = aiohttp.FormData()
        image_bytes = Path(image_path).read_bytes()
        form_data.add_field(
            "image",
            image_bytes,
            filename=Path(image_path).name,
            content_type=_guess_mime(image_path, "image/jpeg"),
        )
        form_data.add_field("output_format", output_format)
        form_data.add_field("normalize", str(normalize).lower())
        form_data.add_field("colormap", colormap)
        return await _request_json("POST", f"{self.base_url}/v1/depth/estimate", data=form_data)


class HailoOllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self.base_url = base_url

    async def version(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/api/version")

    async def tags(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/api/tags")

    async def list_simple(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/hailo/v1/list")

    async def ps(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/api/ps")

    async def show(self, model: str) -> Dict[str, Any]:
        return await _request_json("POST", f"{self.base_url}/api/show", json_body={"model": model})

    async def pull(self, model: str, stream: bool = True) -> Dict[str, Any]:
        payload = {"model": model, "stream": stream}
        if stream:
            text = await _request_text("POST", f"{self.base_url}/api/pull", json_body=payload)
            return {"stream": text}
        return await _request_json("POST", f"{self.base_url}/api/pull", json_body=payload)

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        keep_alive: int = -1,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "keep_alive": keep_alive,
        }
        if options:
            payload["options"] = options
        if stream:
            text = await _request_text("POST", f"{self.base_url}/api/chat", json_body=payload)
            return {"stream": text}
        return await _request_json("POST", f"{self.base_url}/api/chat", json_body=payload)

    async def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
        keep_alive: int = -1,
        suffix: Optional[str] = None,
        format_value: Optional[str] = None,
        raw: Optional[bool] = None,
        template: Optional[str] = None,
        images: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": keep_alive,
        }
        if suffix:
            payload["suffix"] = suffix
        if format_value:
            payload["format"] = format_value
        if raw is not None:
            payload["raw"] = raw
        if template:
            payload["template"] = template
        if images:
            payload["images"] = images
        if options:
            payload["options"] = options
        if stream:
            text = await _request_text("POST", f"{self.base_url}/api/generate", json_body=payload)
            return {"stream": text}
        return await _request_json("POST", f"{self.base_url}/api/generate", json_body=payload)

    async def delete(self, model: str) -> Dict[str, Any]:
        return await _request_json("DELETE", f"{self.base_url}/api/delete", json_body={"model": model})

    async def openai_chat_completions(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        stream: bool = False,
        seed: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        max_tokens: Optional[int] = None,
        n: int = 1,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            "n": n,
        }
        if seed is not None:
            payload["seed"] = seed
        if top_p is not None:
            payload["top_p"] = top_p
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stream:
            text = await _request_text(
                "POST", f"{self.base_url}/v1/chat/completions", json_body=payload
            )
            return {"stream": text}
        return await _request_json(
            "POST", f"{self.base_url}/v1/chat/completions", json_body=payload
        )


class HailoPiperClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5003") -> None:
        self.base_url = base_url

    async def health(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/health")

    async def list_voices(self) -> Dict[str, Any]:
        return await _request_json("GET", f"{self.base_url}/v1/voices")

    async def synthesize_openai(
        self,
        text: str,
        voice: str = "default",
        response_format: str = "wav",
        speed: float = 1.0,
    ) -> bytes:
        payload = {
            "input": text,
            "model": "piper",
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
        }
        return await _request_bytes("POST", f"{self.base_url}/v1/audio/speech", json_body=payload)

    async def synthesize_simple(self, text: str, fmt: str = "wav") -> bytes:
        payload = {"text": text, "format": fmt}
        return await _request_bytes("POST", f"{self.base_url}/v1/synthesize", json_body=payload)
