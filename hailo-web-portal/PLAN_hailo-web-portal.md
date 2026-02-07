# Plan: Unified Hailo Services Web Portal

**Date:** February 6, 2026  
**Author:** Greg  
**Status:** Draft for Implementation  

## Overview

This plan outlines the creation of a unified web portal for testing and managing the Hailo AI system services on Raspberry Pi 5. The portal will provide:

- **Tabbed interface** for testing 8 AI services (ollama, vision, whisper, ocr, clip, pose, depth, piper)
- **Full-featured API coverage** - each tab implements ALL endpoints and parameters documented in that service's API_SPEC.md, as is reasonably supportable by gradio
- **File upload support** for images and audio files (inputs to vision/clip/depth/audio/etc. services)
- **Rich configuration** - all optional parameters exposed as interactive components (sliders, dropdowns, checkboxes)
- **Device status monitor** with auto-refreshing temperature and loaded networks
- **Service control tab** for starting/stopping/restarting services via `sudo systemctl`
- **Ollama conflict prevention** (blocks ollama startup if other services are running)

**Design Philosophy:** The portal should be a comprehensive test interface that exposes the full capabilities of each service, not just basic "hello world" demos. Users should be able to explore all endpoints, tune parameters, and compare results without writing curl commands.

**Technology Stack:**
- **Gradio** for UI components (tabs, file uploads, buttons)
- **FastAPI** for backend endpoints (device status polling, service management)
- **Systemd service** for persistent operation
- **Sudoers configuration** for passwordless systemctl execution

**Target Environment:**
- Raspberry Pi 5 with Hailo-10H NPU
- 64-bit Raspberry Pi OS (Trixie)
- Services deployed as systemd units

**Philosophy:** Pragmatic for personal art projects; not production-grade. Reuse existing API standards; prioritize simplicity over over-engineering.

## Architecture

### High-Level Design

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Gradio UI     │    │   FastAPI Proxy  │    │  Systemd        │
│   (Port 7860)   │◄──►│   (Background)   │◄──►│  Services       │
│                 │    │                  │    │  (Ports 5000,   │
│ • Service Tabs  │    │ • /api/status    │    │   11434-11440)  │
│ • File Uploads  │    │ • /api/services/*│    │                 │
│ • Device Status │    │ • Service Proxy  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

- **Gradio Frontend:** Handles user interactions, file uploads, displays results
- **FastAPI Backend:** Polls device status, manages services via systemctl, proxies requests to individual services
- **Service Integration:** Each service exposes REST APIs; portal acts as HTTP client

### Key Components

1. **app.py** - Main application (Gradio + FastAPI integration)
2. **portal_client.py** - HTTP clients for each service (handles requests/responses)
3. **device_status_monitor.py** - Background polling for device metrics
4. **service_manager.py** - systemctl wrapper with conflict detection
5. **hailo-web-portal.service** - Systemd unit file
6. **install.sh** - Installation script with sudoers setup

### Resource Budget

- **Memory:** <200MB (portal itself) + service memory
- **CPU:** <5% idle, <20% during active polling/testing
- **Thermal:** Monitor via device status; avoid overloading Pi

### Security Considerations

- **Sudoers:** Passwordless systemctl for hailo user (pragmatic for personal use)
- **Network:** Portal binds to 127.0.0.1 (localhost only)
- **No authentication:** Assumes single-user Pi environment

## Implementation Steps

### 1. Create Portal Directory Structure

Create `system_services/hailo-web-portal/` with the following files:

```
hailo-web-portal/
├── app.py                        # Gradio + FastAPI app
├── portal_client.py              # Clients for each service
├── device_status_monitor.py      # Status polling logic
├── service_manager.py            # systemctl wrapper
├── requirements.txt              # Dependencies
├── hailo-web-portal.service      # systemd unit
├── install.sh                    # Installation script
├── README.md                      # Quick start
├── API_SPEC.md                    # Portal endpoints
├── ARCHITECTURE.md                # Design decisions
├── TROUBLESHOOTING.md             # Common issues
└── test_portal.py                # Integration tests
```

### 2. Implement Service Clients (portal_client.py)

Create async HTTP client classes for each service. Each client should implement **all endpoints** documented in that service's API_SPEC.md.

#### Service Capabilities Summary

Based on API_SPEC.md files:

| Service | Port | Key Endpoints | Configuration Parameters |
|---------|------|---------------|-------------------------|
| **hailo-clip** | 5000 | `/v1/classify`, `/v1/embed/image`, `/v1/embed/text` | prompts, top_k, threshold |
| **hailo-vision** | 11435 | `/v1/chat/completions`, `/v1/vision/analyze` | temperature, max_tokens, top_p, stream |
| **hailo-whisper** | 11437 | `/v1/audio/transcriptions` | language, response_format (json/verbose_json/text/srt/vtt), temperature |
| **hailo-ocr** | 11436 | `/v1/ocr/extract` | languages (en/zh) |
| **hailo-pose** | 11440 | `/v1/pose/detect` | confidence_threshold, iou_threshold, max_detections, keypoint_threshold |
| **hailo-depth** | 11439 | `/v1/depth/estimate` | output_format (numpy/image/both), normalize, colormap (viridis/plasma/magma/turbo/jet) |
| **hailo-ollama** | 11434 | `/api/chat`, `/api/generate`, `/api/tags`, `/api/ps` | temperature, seed, top_k, top_p, frequency_penalty, num_predict, keep_alive |
| **hailo-piper** | 5003 | `/v1/audio/speech`, `/v1/synthesize` | speed, response_format (wav/pcm) |

#### Example Client Implementation

```python
import aiohttp
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path

class HailoClipClient:
    """Client for hailo-clip service - zero-shot image classification."""
    BASE_URL = "http://127.0.0.1:5000"
    
    async def classify(
        self,
        image_path: str,
        prompts: List[str],
        top_k: int = 3,
        threshold: float = 0.0
    ) -> Dict[str, Any]:
        """Classify image against text prompts."""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        payload = {
            "image": f"data:image/jpeg;base64,{image_data}",
            "prompts": prompts,
            "top_k": top_k,
            "threshold": threshold
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/classify", json=payload, timeout=30) as resp:
                return await resp.json()
    
    async def embed_image(self, image_path: str) -> Dict[str, Any]:
        """Get CLIP embedding for image."""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        payload = {"image": f"data:image/jpeg;base64,{image_data}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/embed/image", json=payload, timeout=30) as resp:
                return await resp.json()
    
    async def embed_text(self, text: str) -> Dict[str, Any]:
        """Get CLIP embedding for text."""
        payload = {"text": text}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/embed/text", json=payload, timeout=30) as resp:
                return await resp.json()

class HailoVisionClient:
    """Client for hailo-vision service - vision-language model."""
    BASE_URL = "http://127.0.0.1:11435"
    
    async def chat_completion(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 200,
        top_p: float = 0.9,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Chat completion with image context."""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        payload = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/chat/completions", json=payload, timeout=60) as resp:
                return await resp.json()
    
    async def batch_analyze(
        self,
        image_paths: List[str],
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> Dict[str, Any]:
        """Batch analyze multiple images."""
        images = []
        for path in image_paths:
            with open(path, "rb") as f:
                images.append(f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}")
        
        payload = {
            "images": images,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/vision/analyze", json=payload, timeout=120) as resp:
                return await resp.json()

class HailoWhisperClient:
    """Client for hailo-whisper service - speech-to-text."""
    BASE_URL = "http://127.0.0.1:11437"
    
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        response_format: str = "json",
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """Transcribe audio file."""
        form_data = aiohttp.FormData()
        form_data.add_field('file', open(audio_path, 'rb'), filename=Path(audio_path).name)
        form_data.add_field('model', 'Whisper-Base')
        
        if language:
            form_data.add_field('language', language)
        
        form_data.add_field('response_format', response_format)
        form_data.add_field('temperature', str(temperature))
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/audio/transcriptions", data=form_data, timeout=60) as resp:
                if response_format == "text":
                    return {"text": await resp.text()}
                elif response_format in ["srt", "vtt"]:
                    return {"subtitles": await resp.text()}
                else:
                    return await resp.json()

class HailoDepthClient:
    """Client for hailo-depth service - depth estimation."""
    BASE_URL = "http://127.0.0.1:11439"
    
    async def estimate_depth(
        self,
        image_path: str,
        output_format: str = "both",
        normalize: bool = True,
        colormap: str = "viridis"
    ) -> Dict[str, Any]:
        """Estimate depth from image."""
        form_data = aiohttp.FormData()
        form_data.add_field('image', open(image_path, 'rb'), filename=Path(image_path).name)
        form_data.add_field('output_format', output_format)
        form_data.add_field('normalize', str(normalize).lower())
        form_data.add_field('colormap', colormap)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/depth/estimate", data=form_data, timeout=60) as resp:
                return await resp.json()

class HailoOllamaClient:
    """Client for hailo-ollama service - LLM inference."""
    BASE_URL = "http://127.0.0.1:11434"
    
    async def chat(
        self,
        prompt: str,
        model: str = "qwen2.5-instruct:1.5b",
        temperature: float = 0.7,
        max_tokens: int = 200,
        keep_alive: int = -1,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Chat completion."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/api/chat", json=payload, timeout=120) as resp:
                return await resp.json()
    
    async def list_models(self) -> Dict[str, Any]:
        """List available models."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.BASE_URL}/api/tags", timeout=10) as resp:
                return await resp.json()

class HailoPiperClient:
    """Client for hailo-piper service - text-to-speech."""
    BASE_URL = "http://127.0.0.1:5003"
    
    async def synthesize(
        self,
        text: str,
        response_format: str = "wav",
        speed: float = 1.0
    ) -> bytes:
        """Synthesize speech from text."""
        payload = {
            "input": text,
            "model": "piper",
            "response_format": response_format,
            "speed": speed
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.BASE_URL}/v1/audio/speech", json=payload, timeout=30) as resp:
                return await resp.read()

# Additional clients for OCR and Pose follow similar patterns...
```

Each client handles:
- File encoding (images/audio to base64 or multipart)
- Request formatting per service API
- Response parsing (JSON, binary audio, subtitles)
- Error handling (timeouts, HTTP errors)
- All optional parameters from API_SPEC.md

### 3. Implement Device Status Monitor (device_status_monitor.py)

Background polling for device metrics:

```python
import asyncio
import aiohttp
from typing import Dict, Any

class DeviceStatusMonitor:
    def __init__(self):
        self.latest_status: Dict[str, Any] = {}
        self._running = False
    
    async def start_polling(self):
        self._running = True
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://127.0.0.1:5099/v1/device/status") as resp:
                        if resp.status == 200:
                            self.latest_status = await resp.json()
            except Exception as e:
                self.latest_status = {"status": "error", "message": str(e)}
            
            await asyncio.sleep(3)  # Poll every 3 seconds
    
    def stop_polling(self):
        self._running = False
    
    def get_status(self) -> Dict[str, Any]:
        return self.latest_status
```

### 4. Implement Service Manager (service_manager.py)

systemctl wrapper with ollama conflict detection:

```python
import subprocess
import asyncio
from typing import Dict, List

class ServiceManager:
    SERVICES = [
        "device-manager", "hailo-ollama", "hailo-vision", "hailo-whisper",
        "hailo-ocr", "hailo-clip", "hailo-pose", "hailo-depth", "hailo-piper"
    ]
    
    async def get_status(self) -> Dict[str, str]:
        status = {}
        for service in self.SERVICES:
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, subprocess.run,
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True
                )
                status[service] = "running" if result.returncode == 0 else "stopped"
            except Exception:
                status[service] = "error"
        return status
    
    async def start_service(self, service_name: str) -> Dict[str, str]:
        if service_name == "hailo-ollama":
            conflicts = await self._check_ollama_conflicts()
            if conflicts:
                return {
                    "status": "error",
                    "message": f"Cannot start hailo-ollama. These services are running: {', '.join(conflicts)}. Stop them first."
                }
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, subprocess.run,
                ["sudo", "systemctl", "start", service_name],
                check=True
            )
            return {"status": "ok"}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Failed to start {service_name}: {e}"}
    
    async def stop_service(self, service_name: str) -> Dict[str, str]:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, subprocess.run,
                ["sudo", "systemctl", "stop", service_name],
                check=True
            )
            return {"status": "ok"}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Failed to stop {service_name}: {e}"}
    
    async def restart_service(self, service_name: str) -> Dict[str, str]:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, subprocess.run,
                ["sudo", "systemctl", "restart", service_name],
                check=True
            )
            return {"status": "ok"}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Failed to restart {service_name}: {e}"}
    
    async def _check_ollama_conflicts(self) -> List[str]:
        status = await self.get_status()
        running_services = [s for s, stat in status.items() if stat == "running" and s != "hailo-ollama"]
        return running_services
```

### 5. Implement Main App (app.py)

Gradio + FastAPI integration with full-featured service tabs:

```python
import gradio as gr
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import base64
import io
from PIL import Image

from portal_client import *
from device_status_monitor import DeviceStatusMonitor
from service_manager import ServiceManager

# Initialize components
monitor = DeviceStatusMonitor()
service_mgr = ServiceManager()

# Clients
clip_client = HailoClipClient()
vision_client = HailoVisionClient()
whisper_client = HailoWhisperClient()
ocr_client = HailoOCRClient()
pose_client = HailoPoseClient()
depth_client = HailoDepthClient()
ollama_client = HailoOllamaClient()
piper_client = HailoPiperClient()

# FastAPI app
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

@app.get("/api/status")
async def get_device_status():
    return monitor.get_status()

@app.get("/api/services/status")
async def get_services_status():
    return await service_mgr.get_status()

@app.post("/api/services/start/{service_name}")
async def start_service(service_name: str):
    return await service_mgr.start_service(service_name)

@app.post("/api/services/stop/{service_name}")
async def stop_service(service_name: str):
    return await service_mgr.stop_service(service_name)

@app.post("/api/services/restart/{service_name}")
async def restart_service(service_name: str):
    return await service_mgr.restart_service(service_name)

# Gradio interface
def build_gradio_interface():
    with gr.Blocks(title="Hailo AI Services Portal", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# Hailo AI Services Portal")
        gr.Markdown("Comprehensive testing interface for all Hailo-10H AI services on Raspberry Pi 5")
        
        # Device status (persistent header)
        with gr.Row():
            with gr.Column(scale=4):
                status_display = gr.JSON(label="Device Status", value=monitor.get_status())
            with gr.Column(scale=1):
                refresh_status_btn = gr.Button("Refresh Status", size="sm")
        
        # Service tabs
        with gr.Tabs():
            # =====================================================================
            # HAILO-CLIP TAB - Zero-shot Classification + Embeddings
            # =====================================================================
            with gr.TabItem("CLIP (Zero-shot)"):
                gr.Markdown("### Zero-shot Image Classification & Embeddings")
                
                with gr.Tabs():
                    # Sub-tab: Classification
                    with gr.TabItem("Classify"):
                        with gr.Row():
                            with gr.Column():
                                clip_image = gr.Image(label="Upload Image", type="filepath")
                                clip_prompts = gr.Textbox(
                                    label="Text Prompts (one per line)",
                                    placeholder="a photo of a person\na photo of a dog\na photo of a car",
                                    lines=5
                                )
                                with gr.Row():
                                    clip_top_k = gr.Slider(1, 10, value=3, step=1, label="Top K Matches")
                                    clip_threshold = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Confidence")
                                clip_classify_btn = gr.Button("Classify", variant="primary")
                            
                            with gr.Column():
                                clip_result = gr.JSON(label="Classification Results")
                                clip_timing = gr.Textbox(label="Inference Time (ms)", interactive=False)
                        
                        def classify_image(image, prompts_text, top_k, threshold):
                            if not image or not prompts_text:
                                return {"error": "Missing image or prompts"}, ""
                            
                            prompts = [p.strip() for p in prompts_text.split("\n") if p.strip()]
                            result = asyncio.run(clip_client.classify(image, prompts, int(top_k), threshold))
                            
                            timing = f"{result.get('inference_time_ms', 0):.1f} ms"
                            return result, timing
                        
                        clip_classify_btn.click(
                            fn=classify_image,
                            inputs=[clip_image, clip_prompts, clip_top_k, clip_threshold],
                            outputs=[clip_result, clip_timing]
                        )
                    
                    # Sub-tab: Image Embedding
                    with gr.TabItem("Image Embedding"):
                        with gr.Row():
                            with gr.Column():
                                clip_embed_image = gr.Image(label="Upload Image", type="filepath")
                                clip_embed_btn = gr.Button("Get Embedding", variant="primary")
                            
                            with gr.Column():
                                clip_embed_result = gr.JSON(label="Embedding Vector (512-dim)")
                                clip_embed_vis = gr.Textbox(label="First 10 values", interactive=False)
                        
                        def get_image_embedding(image):
                            if not image:
                                return {"error": "Missing image"}, ""
                            
                            result = asyncio.run(clip_client.embed_image(image))
                            preview = str(result.get('embedding', [])[:10])
                            return result, preview
                        
                        clip_embed_btn.click(
                            fn=get_image_embedding,
                            inputs=[clip_embed_image],
                            outputs=[clip_embed_result, clip_embed_vis]
                        )
                    
                    # Sub-tab: Text Embedding
                    with gr.TabItem("Text Embedding"):
                        with gr.Row():
                            with gr.Column():
                                clip_text_input = gr.Textbox(
                                    label="Text",
                                    placeholder="a photo of a person wearing red shirt",
                                    lines=3
                                )
                                clip_text_embed_btn = gr.Button("Get Embedding", variant="primary")
                            
                            with gr.Column():
                                clip_text_embed_result = gr.JSON(label="Embedding Vector (512-dim)")
                        
                        def get_text_embedding(text):
                            if not text:
                                return {"error": "Missing text"}
                            
                            return asyncio.run(clip_client.embed_text(text))
                        
                        clip_text_embed_btn.click(
                            fn=get_text_embedding,
                            inputs=[clip_text_input],
                            outputs=[clip_text_embed_result]
                        )
            
            # =====================================================================
            # HAILO-VISION TAB - Vision-Language Model
            # =====================================================================
            with gr.TabItem("Vision (VLM)"):
                gr.Markdown("### Vision-Language Model - Qwen2-VL-2B")
                
                with gr.Tabs():
                    # Sub-tab: Chat Completion
                    with gr.TabItem("Chat Completion"):
                        with gr.Row():
                            with gr.Column():
                                vision_image = gr.Image(label="Upload Image", type="filepath")
                                vision_prompt = gr.Textbox(
                                    label="Prompt",
                                    placeholder="Describe this image in detail.",
                                    lines=3
                                )
                                with gr.Accordion("Advanced Options", open=False):
                                    vision_temperature = gr.Slider(0.0, 2.0, value=0.7, step=0.1, label="Temperature")
                                    vision_max_tokens = gr.Slider(50, 500, value=200, step=50, label="Max Tokens")
                                    vision_top_p = gr.Slider(0.0, 1.0, value=0.9, step=0.05, label="Top P")
                                vision_chat_btn = gr.Button("Generate Response", variant="primary")
                            
                            with gr.Column():
                                vision_response = gr.Textbox(label="Response", lines=10, interactive=False)
                                vision_timing = gr.Textbox(label="Performance", interactive=False)
                        
                        def vision_chat(image, prompt, temp, max_tok, top_p):
                            if not image or not prompt:
                                return "Missing image or prompt", ""
                            
                            result = asyncio.run(vision_client.chat_completion(
                                image, prompt, temp, int(max_tok), top_p
                            ))
                            
                            response_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                            timing = f"Inference: {result.get('performance', {}).get('inference_time_ms', 0):.1f} ms"
                            return response_text, timing
                        
                        vision_chat_btn.click(
                            fn=vision_chat,
                            inputs=[vision_image, vision_prompt, vision_temperature, vision_max_tokens, vision_top_p],
                            outputs=[vision_response, vision_timing]
                        )
                    
                    # Sub-tab: Batch Analyze
                    with gr.TabItem("Batch Analyze"):
                        with gr.Row():
                            with gr.Column():
                                vision_batch_images = gr.File(label="Upload Images", file_count="multiple", type="filepath")
                                vision_batch_prompt = gr.Textbox(
                                    label="Analysis Prompt",
                                    placeholder="For each image, describe the main objects.",
                                    lines=3
                                )
                                vision_batch_btn = gr.Button("Analyze Batch", variant="primary")
                            
                            with gr.Column():
                                vision_batch_result = gr.JSON(label="Batch Results")
                        
                        def vision_batch(images, prompt):
                            if not images or not prompt:
                                return {"error": "Missing images or prompt"}
                            
                            return asyncio.run(vision_client.batch_analyze(images, prompt))
                        
                        vision_batch_btn.click(
                            fn=vision_batch,
                            inputs=[vision_batch_images, vision_batch_prompt],
                            outputs=[vision_batch_result]
                        )
            
            # =====================================================================
            # HAILO-WHISPER TAB - Speech-to-Text
            # =====================================================================
            with gr.TabItem("Whisper (STT)"):
                gr.Markdown("### Speech-to-Text Transcription")
                
                with gr.Row():
                    with gr.Column():
                        whisper_audio = gr.Audio(label="Upload Audio", type="filepath")
                        with gr.Row():
                            whisper_language = gr.Dropdown(
                                ["Auto-detect", "en", "es", "fr", "de", "zh", "ja", "ko"],
                                value="Auto-detect",
                                label="Language"
                            )
                            whisper_format = gr.Dropdown(
                                ["json", "verbose_json", "text", "srt", "vtt"],
                                value="json",
                                label="Response Format"
                            )
                        whisper_temperature = gr.Slider(0.0, 1.0, value=0.0, step=0.1, label="Temperature")
                        whisper_transcribe_btn = gr.Button("Transcribe", variant="primary")
                    
                    with gr.Column():
                        whisper_result = gr.Textbox(label="Transcription", lines=15, interactive=False)
                        whisper_timing = gr.Textbox(label="Processing Time", interactive=False)
                
                def transcribe_audio(audio, lang, fmt, temp):
                    if not audio:
                        return "No audio file uploaded", ""
                    
                    lang_code = None if lang == "Auto-detect" else lang
                    result = asyncio.run(whisper_client.transcribe(audio, lang_code, fmt, temp))
                    
                    if fmt == "text":
                        output = result.get('text', '')
                    elif fmt in ["srt", "vtt"]:
                        output = result.get('subtitles', '')
                    else:
                        output = str(result)
                    
                    return output, f"Completed in {fmt} format"
                
                whisper_transcribe_btn.click(
                    fn=transcribe_audio,
                    inputs=[whisper_audio, whisper_language, whisper_format, whisper_temperature],
                    outputs=[whisper_result, whisper_timing]
                )
            
            # =====================================================================
            # HAILO-OCR TAB - Text Detection + Recognition
            # =====================================================================
            with gr.TabItem("OCR"):
                gr.Markdown("### Optical Character Recognition")
                
                with gr.Row():
                    with gr.Column():
                        ocr_image = gr.Image(label="Upload Image", type="filepath")
                        ocr_language = gr.Dropdown(
                            ["en", "zh"],
                            value="en",
                            label="Language"
                        )
                        ocr_extract_btn = gr.Button("Extract Text", variant="primary")
                    
                    with gr.Column():
                        ocr_text = gr.Textbox(label="Extracted Text", lines=10, interactive=False)
                        ocr_result = gr.JSON(label="Detection Details")
                        ocr_timing = gr.Textbox(label="Performance", interactive=False)
                
                def extract_text(image, lang):
                    if not image:
                        return "", {"error": "No image"}, ""
                    
                    result = asyncio.run(ocr_client.extract_text(image, [lang]))
                    
                    text = result.get('text', '')
                    timing = f"Detection: {result.get('performance', {}).get('detection_time_ms', 0):.1f} ms, Recognition: {result.get('performance', {}).get('recognition_time_ms', 0):.1f} ms"
                    return text, result, timing
                
                ocr_extract_btn.click(
                    fn=extract_text,
                    inputs=[ocr_image, ocr_language],
                    outputs=[ocr_text, ocr_result, ocr_timing]
                )
            
            # =====================================================================
            # HAILO-POSE TAB - Human Pose Estimation
            # =====================================================================
            with gr.TabItem("Pose"):
                gr.Markdown("### Human Pose Estimation (YOLOv8)")
                
                with gr.Row():
                    with gr.Column():
                        pose_image = gr.Image(label="Upload Image", type="filepath")
                        with gr.Accordion("Detection Parameters", open=True):
                            pose_conf_thresh = gr.Slider(0.0, 1.0, value=0.5, step=0.05, label="Person Confidence")
                            pose_iou_thresh = gr.Slider(0.0, 1.0, value=0.45, step=0.05, label="IoU Threshold")
                            pose_max_det = gr.Slider(1, 20, value=10, step=1, label="Max Detections")
                            pose_kp_thresh = gr.Slider(0.0, 1.0, value=0.3, step=0.05, label="Keypoint Confidence")
                        pose_detect_btn = gr.Button("Detect Poses", variant="primary")
                    
                    with gr.Column():
                        pose_result = gr.JSON(label="Detected Poses")
                        pose_timing = gr.Textbox(label="Inference Time", interactive=False)
                        pose_count = gr.Textbox(label="People Detected", interactive=False)
                
                def detect_poses(image, conf, iou, max_det, kp_thresh):
                    if not image:
                        return {"error": "No image"}, "", ""
                    
                    result = asyncio.run(pose_client.detect_poses(
                        image, conf, iou, int(max_det), kp_thresh
                    ))
                    
                    timing = f"{result.get('inference_time_ms', 0):.1f} ms"
                    count = f"{result.get('count', 0)} people"
                    return result, timing, count
                
                pose_detect_btn.click(
                    fn=detect_poses,
                    inputs=[pose_image, pose_conf_thresh, pose_iou_thresh, pose_max_det, pose_kp_thresh],
                    outputs=[pose_result, pose_timing, pose_count]
                )
            
            # =====================================================================
            # HAILO-DEPTH TAB - Depth Estimation
            # =====================================================================
            with gr.TabItem("Depth"):
                gr.Markdown("### Monocular Depth Estimation")
                
                with gr.Row():
                    with gr.Column():
                        depth_image = gr.Image(label="Upload Image", type="filepath")
                        with gr.Row():
                            depth_format = gr.Dropdown(
                                ["numpy", "image", "both"],
                                value="both",
                                label="Output Format"
                            )
                            depth_colormap = gr.Dropdown(
                                ["viridis", "plasma", "magma", "turbo", "jet"],
                                value="viridis",
                                label="Colormap"
                            )
                        depth_normalize = gr.Checkbox(label="Normalize Depth", value=True)
                        depth_estimate_btn = gr.Button("Estimate Depth", variant="primary")
                    
                    with gr.Column():
                        depth_viz = gr.Image(label="Depth Visualization")
                        depth_result = gr.JSON(label="Depth Results")
                        depth_timing = gr.Textbox(label="Inference Time", interactive=False)
                
                def estimate_depth(image, fmt, colormap, normalize):
                    if not image:
                        return None, {"error": "No image"}, ""
                    
                    result = asyncio.run(depth_client.estimate_depth(image, fmt, normalize, colormap))
                    
                    # Decode depth visualization if available
                    depth_img = None
                    if 'depth_image' in result:
                        img_data = base64.b64decode(result['depth_image'])
                        depth_img = Image.open(io.BytesIO(img_data))
                    
                    timing = f"{result.get('inference_time_ms', 0):.1f} ms"
                    return depth_img, result, timing
                
                depth_estimate_btn.click(
                    fn=estimate_depth,
                    inputs=[depth_image, depth_format, depth_colormap, depth_normalize],
                    outputs=[depth_viz, depth_result, depth_timing]
                )
            
            # =====================================================================
            # HAILO-OLLAMA TAB - LLM Chat
            # =====================================================================
            with gr.TabItem("Ollama (LLM)"):
                gr.Markdown("### Large Language Model Chat")
                gr.Markdown("⚠️ **Warning:** Ollama requires exclusive device access. Stop other services first.")
                
                with gr.Row():
                    with gr.Column():
                        ollama_model_list = gr.Dropdown(
                            [],  # Populated dynamically
                            label="Select Model",
                            interactive=True
                        )
                        ollama_refresh_models = gr.Button("Refresh Models", size="sm")
                        ollama_prompt = gr.Textbox(
                            label="Prompt",
                            placeholder="Enter your question or prompt...",
                            lines=5
                        )
                        with gr.Accordion("Generation Options", open=False):
                            ollama_temperature = gr.Slider(0.0, 2.0, value=0.7, step=0.1, label="Temperature")
                            ollama_max_tokens = gr.Slider(50, 500, value=200, step=50, label="Max Tokens")
                            ollama_keep_alive = gr.Radio(
                                choices=["-1 (Keep loaded)", "0 (Unload after)", "300 (5 min)"],
                                value="-1 (Keep loaded)",
                                label="Keep Alive"
                            )
                        ollama_generate_btn = gr.Button("Generate", variant="primary")
                    
                    with gr.Column():
                        ollama_response = gr.Textbox(label="Response", lines=15, interactive=False)
                        ollama_timing = gr.Textbox(label="Performance", interactive=False)
                
                def list_ollama_models():
                    result = asyncio.run(ollama_client.list_models())
                    models = [m['name'] for m in result.get('models', [])]
                    return gr.Dropdown(choices=models, value=models[0] if models else None)
                
                def ollama_generate(model, prompt, temp, max_tok, keep_alive_str):
                    if not model or not prompt:
                        return "Missing model or prompt", ""
                    
                    keep_alive_val = int(keep_alive_str.split()[0])
                    result = asyncio.run(ollama_client.chat(prompt, model, temp, int(max_tok), keep_alive_val))
                    
                    response = result.get('message', {}).get('content', '')
                    timing = f"Total: {result.get('total_duration', 0) / 1e6:.0f} ms, Eval: {result.get('eval_duration', 0) / 1e6:.0f} ms"
                    return response, timing
                
                ollama_refresh_models.click(
                    fn=list_ollama_models,
                    outputs=[ollama_model_list]
                )
                
                ollama_generate_btn.click(
                    fn=ollama_generate,
                    inputs=[ollama_model_list, ollama_prompt, ollama_temperature, ollama_max_tokens, ollama_keep_alive],
                    outputs=[ollama_response, ollama_timing]
                )
            
            # =====================================================================
            # HAILO-PIPER TAB - Text-to-Speech
            # =====================================================================
            with gr.TabItem("Piper (TTS)"):
                gr.Markdown("### Text-to-Speech Synthesis")
                
                with gr.Row():
                    with gr.Column():
                        piper_text = gr.Textbox(
                            label="Text to Synthesize",
                            placeholder="Enter text (max 5000 characters)...",
                            lines=5
                        )
                        with gr.Row():
                            piper_format = gr.Dropdown(
                                ["wav", "pcm"],
                                value="wav",
                                label="Format"
                            )
                            piper_speed = gr.Slider(0.5, 2.0, value=1.0, step=0.1, label="Speed")
                        piper_synthesize_btn = gr.Button("Synthesize", variant="primary")
                    
                    with gr.Column():
                        piper_audio = gr.Audio(label="Generated Audio", type="numpy")
                        piper_status = gr.Textbox(label="Status", interactive=False)
                
                def synthesize_speech(text, fmt, speed):
                    if not text:
                        return None, "No text provided"
                    
                    audio_bytes = asyncio.run(piper_client.synthesize(text, fmt, speed))
                    
                    # Convert to format Gradio expects
                    # For simplicity, save to temp file and return path
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(audio_bytes)
                        audio_path = f.name
                    
                    return audio_path, f"Synthesized {len(text)} characters"
                
                piper_synthesize_btn.click(
                    fn=synthesize_speech,
                    inputs=[piper_text, piper_format, piper_speed],
                    outputs=[piper_audio, piper_status]
                )
            
            # =====================================================================
            # SERVICE CONTROL TAB
            # =====================================================================
            with gr.TabItem("Service Control"):
                gr.Markdown("### System Service Management")
                gr.Markdown("⚠️ **hailo-ollama requires exclusive device access.** Starting ollama will require stopping other services first.")
                
                services_status = gr.Dataframe(
                    headers=["Service", "Status"],
                    value=[],
                    interactive=False
                )
                
                with gr.Row():
                    refresh_services_btn = gr.Button("Refresh Status")
                    start_all_btn = gr.Button("Start All (except ollama)")
                    stop_all_btn = gr.Button("Stop All")
                
                # Individual service controls (simplified; expand with buttons per service)
                service_action_result = gr.Textbox(label="Action Result", interactive=False)
                
                def refresh_services():
                    status = asyncio.run(service_mgr.get_status())
                    data = [[name, stat] for name, stat in status.items()]
                    return data
                
                refresh_services_btn.click(
                    fn=refresh_services,
                    outputs=[services_status]
                )
        
        # Auto-refresh device status
        def update_status():
            return monitor.get_status()
        
        refresh_status_btn.click(fn=update_status, outputs=[status_display])
        
        # Auto-refresh on load
        demo.load(fn=update_status, outputs=[status_display])
    
    return demo

# Mount Gradio
gradio_demo = build_gradio_interface()
app = gr.mount_gradio_app(app, gradio_demo, path="/")

# Start polling in background
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitor.start_polling())

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7860)
```

**Key Implementation Features:**

1. **Full API Coverage:** Each tab implements ALL endpoints from that service's API_SPEC.md2. **Sub-tabs for Complex Services:** CLIP (classify/embed/text), Vision (chat/batch), etc.
3. **All Parameters Exposed:** Sliders, dropdowns, checkboxes for every optional parameter
4. **Advanced Options:** Collapsible accordions for less common parameters
5. **Real-time Feedback:** Timing metrics, result previews, error messages
6. **File Handling:** Images and audio uploaded via Gradio's native components
7. **Response Visualization:** JSON for structured data, text for simple output, images for depth/pose results

### 6. Create Systemd Service (hailo-web-portal.service)

```
[Unit]
Description=Hailo Web Portal for AI Services
After=device-manager.service
Requires=device-manager.service

[Service]
Type=simple
User=hailo
Group=hailo
ExecStart=/opt/hailo-web-portal/venv/bin/python /opt/hailo-web-portal/app.py
WorkingDirectory=/opt/hailo-web-portal
Restart=always
RestartSec=5
MemoryLimit=200M
CPUQuota=20%

[Install]
WantedBy=multi-user.target
```

### 7. Create Installation Script (install.sh)

```bash
#!/bin/bash
set -e

# Create venv
sudo mkdir -p /opt/hailo-web-portal
sudo chown hailo:hailo /opt/hailo-web-portal
cd /opt/hailo-web-portal

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy files (assume run from repo)
cp -r /path/to/repo/system_services/hailo-web-portal/* .

# Configure sudoers
echo "hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hailo-*" | sudo tee -a /etc/sudoers.d/hailo-systemctl > /dev/null
echo "hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hailo-*" | sudo tee -a /etc/sudoers.d/hailo-systemctl > /dev/null
echo "hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hailo-*" | sudo tee -a /etc/sudoers.d/hailo-systemctl > /dev/null
echo "hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl status hailo-*" | sudo tee -a /etc/sudoers.d/hailo-systemctl > /dev/null
sudo chmod 0440 /etc/sudoers.d/hailo-systemctl

# Install systemd unit
sudo cp hailo-web-portal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hailo-web-portal
sudo systemctl start hailo-web-portal
```

### 8. Create Requirements (requirements.txt)

```
gradio==4.30.0
fastapi==0.110.0
uvicorn==0.27.0
aiohttp==3.9.3
pillow==10.1.0
python-multipart==0.0.6
```

### 9. Create Documentation

- **README.md:** Installation, usage, port info
- **API_SPEC.md:** Portal endpoints (/api/status, /api/services/*)
- **ARCHITECTURE.md:** Design rationale, ollama constraint, resource model
- **TROUBLESHOOTING.md:** Sudo errors, service conflicts, port issues

### 10. Create Test Suite (test_portal.py)

```python
import pytest
import aiohttp
from service_manager import ServiceManager

@pytest.mark.asyncio
async def test_device_status_endpoint():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:7860/api/status") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "temperature_c" in data

@pytest.mark.asyncio
async def test_service_status():
    mgr = ServiceManager()
    status = await mgr.get_status()
    assert isinstance(status, dict)
    assert "hailo-ollama" in status

@pytest.mark.asyncio
async def test_ollama_conflict():
    mgr = ServiceManager()
    # Assume hailo-vision is running
    conflicts = await mgr._check_ollama_conflicts()
    # Test logic...
```

## Verification

### Manual Testing

1. **Install and start:**
   ```bash
   cd system_services/hailo-web-portal
   sudo bash install.sh
   ```

2. **Access portal:** http://localhost:7860/ui

3. **Test device status:** Verify temperature updates every 3s

4. **Test service tabs:** Upload image to Vision tab, verify response

5. **Test service control:**
   - Start hailo-clip → status turns green
   - Try to start hailo-ollama → error message
   - Stop hailo-clip → start ollama → success

6. **Check logs:** `journalctl -u hailo-web-portal -f`

### Automated Testing

```bash
cd system_services/hailo-web-portal
pytest test_portal.py -v
```

## Decisions

- **Gradio + FastAPI hybrid:** Gradio provides rich UI components for files + tabs with minimal code; FastAPI's async background task efficiently polls device status without blocking the Gradio server
  - *Alternative considered:* Pure Flask + Jinja2 templates (more code, less native file handling); dropped in favor of speed
  
- **Full API coverage:** Each service tab implements ALL endpoints and parameters from its API_SPEC.md, not just basic demos
  - *Rationale:* Portal should be a comprehensive testing tool, not just a "hello world" showcase. Users can explore all capabilities without writing curl commands
  - *Example:* CLIP tab has 3 sub-tabs (classify, image embed, text embed); Depth tab exposes all colormaps and output formats
  
- **Sub-tabs for multi-endpoint services:** Services with 2+ major endpoints (CLIP, Vision, Whisper) get sub-tabs for organization
  - *Trade-off:* More clicks to navigate, but clearer separation of concerns
  
- **Advanced options in accordions:** Less common parameters (temperature, top_p, etc.) are collapsible to reduce visual clutter
  - *Balance:* Power users can access all options; casual users aren't overwhelmed
  
- **8 services included** (ollama, vision, whisper, ocr, clip, pose, depth, piper): Matches production + piper scope. Draft services (face, scrfd, florence) excluded pending completion
  
- **Auto-refresh device status every 3s:** Balances real-time feedback with Pi resource overhead (<1% CPU for polling)
  
- **Block ollama startup:** Prevents device contention; requires explicit user action to stop other services first
  - *Alternative considered:* Auto-stopping services (rejected as less predictable)
  
- **Systemd service**, not manual tool: Persistent, auto-restart on reboot/crash, integrates with system_services/ pattern
  
- **Port 7860:** Gradio default; avoid conflicts with service ports (5000, 11434-11440)

- **Response visualization:** Depth estimates show colorized PNG, pose results show JSON with keypoints, whisper supports subtitle formats (SRT/VTT)

## Risks and Mitigations

- **Resource overload:** Monitor CPU/memory; add rate limiting if needed
- **Sudo security:** Document as personal-use only; no multi-user support
- **Service conflicts:** Clear error messages; user must manually resolve
- **API changes:** Pin dependency versions; test against current service APIs

## Next Steps

1. Implement portal_client.py with all service clients (8 services × multiple endpoints each)
2. Build Gradio interface with tabs and file uploads (reference API_SPEC.md for each service)
3. Integrate FastAPI endpoints and polling
4. Test service management and conflict detection
5. Create documentation and tests
6. Deploy and verify on Pi hardware

---

## Important Notes

### File Uploads

File uploads in the portal refer specifically to **images and audio files** that serve as inputs to the AI services:
- **Images:** For vision, clip, ocr, pose, depth services
- **Audio:** For whisper (speech-to-text) service

The portal is NOT a general-purpose file manager. Users upload images/audio to test inference endpoints.

### API Coverage Philosophy

The portal's tabs should **richly represent all use cases** documented in each service's `API_SPEC.md`:

```bash
system_services/hailo-clip/API_SPEC.md       # 3 endpoints: classify, embed/image, embed/text
system_services/hailo-depth/API_SPEC.md      # 1 endpoint with 5 colormaps + 3 output formats
system_services/hailo-ocr/API_SPEC.md        # 1 endpoint with language selection
system_services/hailo-ollama/API_SPEC.md     # 6+ endpoints: chat, generate, tags, ps, show, pull
system_services/hailo-piper/API_SPEC.md      # 2 endpoints: speech, synthesize (with voice selection)
system_services/hailo-pose/API_SPEC.md       # 1 endpoint with 4 threshold parameters
system_services/hailo-vision/API_SPEC.md     # 2 endpoints: chat/completions, vision/analyze
system_services/hailo-whisper/API_SPEC.md    # 1 endpoint with 5 response formats
```

**Implementation Principle:** Each tab should be as full-featured as reasonably possible, exposing:
- All major endpoints (as sub-tabs if 2+)
- All parameters (required and optional)
- All response formats/options
- Result visualization appropriate to the data type

This ensures the portal is a **comprehensive testing tool**, not a minimal demo. Users should be able to explore the full capabilities of each service without dropping to curl/scripts.

### Services Not Yet Included

The following services have API_SPEC.md files but are excluded from the initial portal implementation due to incomplete implementation or compatibility issues:

- **hailo-face:** Draft stage (installer complete, but needs testing)
- **hailo-scrfd:** Draft stage (specialized face detection, overlaps with hailo-face)
- **hailo-florence:** Installer complete, but has HEF compatibility issues (as noted in research)

These can be added to the portal once they reach production stability. The portal architecture (tabs + clients) makes it easy to add new services incrementally.

---

**Last Updated:** February 7, 2026