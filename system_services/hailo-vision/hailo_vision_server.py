#!/usr/bin/env python3
"""
Hailo Vision Service - Qwen VLM on Hailo-10H

REST API server exposing vision inference via chat-based interface.
Compatible with OpenAI Chat Completions API.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from aiohttp import web
    import yaml
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip3 install aiohttp pyyaml")
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

class VisionService:
    """Vision inference service with model lifecycle management."""
    
    def __init__(self, config: VisionServiceConfig):
        self.config = config
        self.model = None
        self.is_loaded = False
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
    
    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing model: {self.config.model_name}")
        
        try:
            # TODO: Implement HailoRT VLM model loading
            # This is a placeholder for the actual Hailo VLM integration
            # In production, this would:
            # 1. Load the model via HailoRT SDK
            # 2. Initialize NPU device
            # 3. Verify device memory
            
            logger.info("Model initialization placeholder (HailoRT VLM)")
            self.is_loaded = True
            
        except Exception as e:
            logger.error(f"Model initialization failed: {e}")
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
        
        # Use config defaults if not provided
        temperature = temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens
        top_p = top_p or self.config.top_p
        seed = seed or self.config.seed
        
        try:
            # TODO: Implement actual VLM inference
            # This is a placeholder for HailoRT VLM inference
            # In production, this would:
            # 1. Load and decode image from URL/base64
            # 2. Prepare image + text inputs for VLM
            # 3. Run inference on NPU via HailoRT
            # 4. Decode output tokens to text
            
            response = {
                "content": "[Vision model placeholder response]",
                "tokens_generated": 5,
                "inference_time_ms": 450
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise
    
    async def shutdown(self):
        """Unload model and clean up resources."""
        if self.model:
            logger.info("Unloading model")
            # TODO: Properly unload HailoRT model
            self.model = None
            self.is_loaded = False

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
        
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, str):
                    text_prompt = content
                elif isinstance(content, list):
                    for item in content:
                        if item.get("type") == "image":
                            img_url_obj = item.get("image_url", {})
                            image_url = img_url_obj.get("url") if isinstance(img_url_obj, dict) else img_url_obj
                        elif item.get("type") == "text":
                            text_prompt = item.get("text", "")
        
        if not image_url or not text_prompt:
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

async def create_app(service: VisionService) -> web.Application:
    """Create aiohttp application."""
    handler = APIHandler(service)
    app = web.Application()
    
    # Routes
    app.router.add_get('/health', handler.health)
    app.router.add_get('/health/ready', handler.health_ready)
    app.router.add_get('/v1/models', handler.list_models)
    app.router.add_post('/v1/chat/completions', handler.chat_completions)
    
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
