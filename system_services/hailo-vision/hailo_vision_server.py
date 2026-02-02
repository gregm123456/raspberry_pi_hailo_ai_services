#!/usr/bin/env python3
"""
Hailo Vision Service - Qwen VLM on Hailo-10H

REST API server exposing vision inference via chat-based interface.
Compatible with OpenAI Chat Completions API.
"""

import asyncio
import base64
import io
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from aiohttp import web
    import cv2
    import numpy as np
    import requests
    import yaml
    from PIL import Image
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip3 install aiohttp pyyaml pillow numpy opencv-python requests")
    sys.exit(1)

try:
    from device_client import HailoDeviceClient
except ImportError as e:
    print(f"Error: device client not found: {e}")
    print("Ensure device_client.py is available alongside hailo_vision_server.py")
    sys.exit(1)

try:
    from hailo_apps.python.core.common.core import resolve_hef_path
    from hailo_apps.python.core.common.defines import VLM_CHAT_APP, HAILO10H_ARCH
except ImportError as e:
    print(f"Error: hailo-apps not found: {e}")
    print("This service requires hailo-apps package.")
    print("Install with: pip3 install hailo-apps or install from source")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('hailo-vision')

# Configuration paths
XDG_CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', '/etc/xdg')
CONFIG_JSON = os.path.join(XDG_CONFIG_HOME, 'hailo-vision', 'hailo-vision.json')

class VisionServiceConfig:
    """Configuration management."""
    
    def __init__(self):
        self.server_host = "0.0.0.0"
        self.server_port = 11435
        self.model_name = "qwen2-vl-2b-instruct"
        self.hef_path = None  # Will be resolved via hailo-apps
        self.keep_alive = -1
        self.temperature = 0.7
        self.max_tokens = 200
        self.top_p = 0.9
        self.seed = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON."""
        if not os.path.exists(CONFIG_JSON):
            logger.warning(f"Config not found at {CONFIG_JSON}, using defaults")
            return
        
        try:
            with open(CONFIG_JSON, 'r') as f:
                config = json.load(f)
            
            # Parse server config
            server = config.get('server', {})
            self.server_host = server.get('host', self.server_host)
            self.server_port = server.get('port', self.server_port)
            
            # Parse model config
            model = config.get('model', {})
            self.model_name = model.get('name', self.model_name)
            self.hef_path = model.get('hef_path', self.hef_path)
            self.keep_alive = model.get('keep_alive', self.keep_alive)
            
            # Parse generation config
            gen = config.get('generation', {})
            self.temperature = gen.get('temperature', self.temperature)
            self.max_tokens = gen.get('max_tokens', self.max_tokens)
            self.top_p = gen.get('top_p', self.top_p)
            self.seed = gen.get('seed', self.seed)
            
            logger.info(f"Loaded config from {CONFIG_JSON}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

def decode_image_from_url(image_url: str) -> np.ndarray:
    """Decode image from URL or base64 data URI."""
    
    if image_url.startswith('data:image'):
        # Handle base64 data URI
        header, encoded = image_url.split(',', 1)
        image_data = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(image_data))
        return np.array(image)
    elif image_url.startswith('http://') or image_url.startswith('https://'):
        # Handle HTTP/HTTPS URL
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        return np.array(image)
    elif image_url.startswith('file://'):
        # Handle file:// URI
        file_path = image_url[7:]  # Remove 'file://'
        image = Image.open(file_path)
        return np.array(image)
    else:
        # Assume it's a file path
        image = Image.open(image_url)
        return np.array(image)


def preprocess_image_for_vlm(image_array: np.ndarray, target_size: tuple = (336, 336)) -> np.ndarray:
    """Preprocess image for VLM inference using central crop.
    
    Args:
        image_array: Input image in any format (RGB, BGR, RGBA, etc.)
        target_size: Target size (width, height), default (336, 336)
    
    Returns:
        Preprocessed RGB image as uint8 numpy array
    """
    # Convert to RGB if needed
    if len(image_array.shape) == 2:
        # Grayscale to RGB
        image_array = cv2.cvtColor(image_array, cv2.COLOR_GRAY2RGB)
    elif len(image_array.shape) == 3:
        if image_array.shape[2] == 4:
            # RGBA to RGB
            image_array = cv2.cvtColor(image_array, cv2.COLOR_RGBA2RGB)
        elif image_array.shape[2] == 3:
            # Assume BGR (OpenCV default) - convert to RGB
            # PIL images are already RGB, but we can't tell, so we check pixel order
            # Safe approach: always convert from BGR to RGB for consistency
            image_array = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
    
    h, w = image_array.shape[:2]
    target_w, target_h = target_size
    
    # Scale to cover the target size (Central Crop strategy)
    scale = max(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    # Resize the image
    resized = cv2.resize(image_array, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    # Center crop
    x_start = (new_w - target_w) // 2
    y_start = (new_h - target_h) // 2
    cropped = resized[y_start:y_start+target_h, x_start:x_start+target_w]
    
    return cropped.astype(np.uint8)


class VisionService:
    """Vision inference service with model lifecycle management."""
    
    def __init__(self, config: VisionServiceConfig):
        self.config = config
        self.client: Optional[HailoDeviceClient] = None
        self.is_loaded = False
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
        self.hef_path = None
    
    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing model: {self.config.model_name}")
        
        try:
            # Resolve HEF path using hailo-apps resolver
            logger.info("Resolving HEF model path...")
            self.hef_path = resolve_hef_path(
                hef_path=self.config.hef_path,
                app_name=VLM_CHAT_APP,
                arch=HAILO10H_ARCH
            )
            
            if self.hef_path is None:
                raise RuntimeError("Failed to resolve HEF model path. Model may need to be downloaded.")
            
            logger.info(f"Using HEF model: {self.hef_path}")

            logger.info("Connecting to device manager...")
            self.client = HailoDeviceClient()
            await self.client.connect()

            logger.info("Loading VLM model via device manager...")
            start_time = time.time()
            await self.client.load_model(str(self.hef_path), model_type="vlm_chat")
            self.load_time_ms = int((time.time() - start_time) * 1000)
            logger.info("VLM model loaded successfully in %dms", self.load_time_ms)
            
            self.is_loaded = True
            
        except Exception as e:
            logger.error(f"Model initialization failed: {e}", exc_info=True)
            # Cleanup on failure
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            raise
    
    async def process_image(
        self,
        image_url: str,
        text_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        top_p: float = None,
        seed: int = None
    ) -> Dict[str, Any]:
        """Process image with text prompt via VLM."""
        
        if not self.is_loaded:
            raise RuntimeError("Model not loaded")
        if not self.client:
            raise RuntimeError("Device manager client not initialized")
        
        # Use config defaults if not provided
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        top_p = top_p if top_p is not None else self.config.top_p
        seed = seed if seed is not None else self.config.seed
        
        try:
            # 1. Load and decode image from URL/base64
            logger.debug(f"Decoding image from URL (length: {len(image_url)} chars)")
            image_array = decode_image_from_url(image_url)
            logger.debug(f"Image decoded: shape={image_array.shape}, dtype={image_array.dtype}")
            
            # 2. Preprocess image for VLM
            logger.debug("Preprocessing image for VLM...")
            preprocessed_image = preprocess_image_for_vlm(image_array)
            logger.debug(f"Image preprocessed: shape={preprocessed_image.shape}")
            
            # 3. Prepare prompt in VLM format
            prompt = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "You are a helpful assistant that analyzes images and answers questions about them."}]
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": text_prompt}
                    ]
                }
            ]
            
            # 4. Run inference on NPU via HailoRT
            logger.debug(f"Running VLM inference with prompt: '{text_prompt}'")
            start_time = time.time()
            
            response = await self.client.infer(
                str(self.hef_path),
                {
                    "prompt": prompt,
                    "frames": [encode_tensor(preprocessed_image)],
                    "temperature": temperature,
                    "seed": seed,
                    "max_generated_tokens": max_tokens,
                },
                model_type="vlm_chat",
            )
            
            inference_time_ms = response.get("inference_time_ms")
            response_text = response.get("result", "")
            
            # 6. Parse response (remove special tokens)
            # VLM output may contain special tokens like <|im_end|>
            cleaned_response = response_text.split("<|im_end|>")[0].strip()
            
            # Estimate token count (rough approximation: ~4 chars per token)
            tokens_generated = len(cleaned_response) // 4
            
            logger.info(f"VLM inference completed in {inference_time_ms}ms, generated ~{tokens_generated} tokens")
            
            response = {
                "content": cleaned_response,
                "tokens_generated": tokens_generated,
                "inference_time_ms": inference_time_ms
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            raise
    
    async def shutdown(self):
        """Unload model and clean up resources."""
        logger.info("Shutting down VLM service...")

        if self.client:
            try:
                logger.info("Disconnecting from device manager...")
                await self.client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting device client: {e}")
            finally:
                self.client = None
        
        self.is_loaded = False
        logger.info("Shutdown complete")


def encode_tensor(array: np.ndarray) -> Dict[str, Any]:
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }

class APIHandler:
    """HTTP API request handlers."""
    
    def __init__(self, service: VisionService):
        self.service = service
    
    async def health(self, request: web.Request) -> web.Response:
        """GET /health - Service status."""
        return web.json_response({
            "status": "ok",
            "model": self.service.config.model_name,
            "model_loaded": self.service.is_loaded,
            "uptime_seconds": (datetime.utcnow() - self.service.startup_time).total_seconds()
        })
    
    async def health_ready(self, request: web.Request) -> web.Response:
        """GET /health/ready - Readiness probe."""
        if self.service.is_loaded:
            return web.json_response({"ready": True})
        else:
            return web.json_response(
                {"ready": False, "reason": "model_loading"},
                status=503
            )
    
    async def list_models(self, request: web.Request) -> web.Response:
        """GET /v1/models - List available models."""
        return web.json_response({
            "data": [
                {
                    "id": self.service.config.model_name,
                    "object": "model",
                    "created": int(self.service.startup_time.timestamp()),
                    "owned_by": "hailo"
                }
            ],
            "object": "list"
        })
    
    async def chat_completions(self, request: web.Request) -> web.Response:
        """POST /v1/chat/completions - Vision inference."""
        
        try:
            payload = await request.json()
        except Exception as e:
            return web.json_response(
                {"error": {"message": f"Invalid JSON: {e}", "type": "invalid_request_error"}},
                status=400
            )
        
        # Validate required fields
        model = payload.get("model")
        messages = payload.get("messages", [])
        stream = payload.get("stream", False)
        
        if not model:
            return web.json_response(
                {"error": {"message": "Missing 'model' field", "type": "invalid_request_error"}},
                status=400
            )
        
        if not messages:
            return web.json_response(
                {"error": {"message": "Missing 'messages' field", "type": "invalid_request_error"}},
                status=400
            )
        
        # Extract image and text from messages
        image_url = None
        text_prompt = None
        
        logger.debug(f"Parsing {len(messages)} messages for content")
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, str):
                    text_prompt = content
                    logger.debug(f"Found string text prompt: {text_prompt[:50]}...")
                elif isinstance(content, list):
                    for item in content:
                        item_type = item.get("type")
                        if item_type == "image_url":
                            img_url_obj = item.get("image_url", {})
                            url = img_url_obj.get("url") if isinstance(img_url_obj, dict) else img_url_obj
                            if url:
                                image_url = url
                                logger.debug(f"Found image_url item: {image_url[:50]}...")
                        elif item_type == "image":
                            # Support bundled base64 or source
                            data = item.get("image") or item.get("data") or item.get("source")
                            if data:
                                # If it doesn't have the prefix, add it if it looks like base64
                                if isinstance(data, str) and not data.startswith('data:'):
                                    image_url = f"data:image/jpeg;base64,{data}"
                                else:
                                    image_url = data
                                logger.debug(f"Found bundled image item: {image_url[:50]}...")
                        elif item_type == "text":
                            text_prompt = item.get("text", "")
                            logger.debug(f"Found text item: {text_prompt[:50]}...")
        
        if not image_url or not text_prompt:
            logger.warning(f"Incomplete request: image_url={'found' if image_url else 'missing'}, text_prompt={'found' if text_prompt else 'missing'}")
            return web.json_response(
                {"error": {"message": "Message must contain both image and text", "type": "invalid_request_error"}},
                status=400
            )
        
        # Extract generation parameters
        temperature = payload.get("temperature", self.service.config.temperature)
        max_tokens = payload.get("max_tokens", self.service.config.max_tokens)
        top_p = payload.get("top_p", self.service.config.top_p)
        seed = payload.get("seed", self.service.config.seed)
        
        # Run inference
        try:
            result = await self.service.process_image(
                image_url=image_url,
                text_prompt=text_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                seed=seed
            )
            
            response = {
                "id": f"chatcmpl-{datetime.utcnow().timestamp()}",
                "object": "chat.completion",
                "created": int(datetime.utcnow().timestamp()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result["content"]
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 256,  # TODO: Calculate actual prompt tokens
                    "completion_tokens": result["tokens_generated"],
                    "total_tokens": 256 + result["tokens_generated"]
                },
                "performance": {
                    "inference_time_ms": result["inference_time_ms"],
                    "load_time_ms": 0
                }
            }
            
            return web.json_response(response)
            
        except Exception as e:
            logger.error(f"Inference error: {e}")
            return web.json_response(
                {"error": {"message": str(e), "type": "internal_error"}},
                status=500
            )

    async def analyze(self, request: web.Request) -> web.Response:
        """POST /v1/vision/analyze - Batch image analysis."""
        
        try:
            payload = await request.json()
        except Exception as e:
            return web.json_response(
                {"error": {"message": f"Invalid JSON: {e}", "type": "invalid_request_error"}},
                status=400
            )
        
        images = payload.get("images", [])
        prompt = payload.get("prompt")
        
        if not images:
            return web.json_response(
                {"error": {"message": "Missing 'images' field", "type": "invalid_request_error"}},
                status=400
            )
        
        if not prompt:
            return web.json_response(
                {"error": {"message": "Missing 'prompt' field", "type": "invalid_request_error"}},
                status=400
            )
        
        # Extract generation parameters
        temperature = payload.get("temperature", self.service.config.temperature)
        max_tokens = payload.get("max_tokens", self.service.config.max_tokens)
        
        results = []
        total_inference_time = 0
        
        try:
            for image_url in images:
                result = await self.service.process_image(
                    image_url=image_url,
                    text_prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                results.append({
                    "image_url": image_url[:100] + "..." if len(image_url) > 100 else image_url,
                    "analysis": result["content"]
                })
                total_inference_time += result["inference_time_ms"]
            
            return web.json_response({
                "results": results,
                "total_inference_time_ms": total_inference_time
            })
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return web.json_response(
                {"error": {"message": str(e), "type": "internal_error"}},
                status=500
            )

async def create_app(service: VisionService) -> web.Application:
    """Create aiohttp application."""
    handler = APIHandler(service)
    # Increase client_max_size to handle large images (64MB)
    app = web.Application(client_max_size=1024**2 * 64)
    
    # Routes
    app.router.add_get('/health', handler.health)
    app.router.add_get('/health/ready', handler.health_ready)
    app.router.add_get('/v1/models', handler.list_models)
    app.router.add_post('/v1/chat/completions', handler.chat_completions)
    app.router.add_post('/v1/vision/analyze', handler.analyze)
    
    return app

async def main():
    """Main entry point."""
    try:
        # Load configuration
        config = VisionServiceConfig()
        logger.info(f"Hailo Vision Service starting")
        logger.info(f"Server: {config.server_host}:{config.server_port}")
        logger.info(f"Model: {config.model_name}")
        
        # Initialize service
        service = VisionService(config)
        await service.initialize()
        
        # Create and start server
        app = await create_app(service)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.server_host, config.server_port)
        await site.start()
        
        logger.info(f"Service ready at http://{config.server_host}:{config.server_port}")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
    
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await service.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
