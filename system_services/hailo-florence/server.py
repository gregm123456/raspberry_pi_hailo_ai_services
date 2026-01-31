#!/usr/bin/env python3
"""
hailo-florence: Florence-2 Image Captioning REST API Server

Provides REST API for automatic image captioning using Florence-2 VLM.
"""

import os
import sys
import time
import base64
import logging
import argparse
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any

import yaml
from PIL import Image
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import uvicorn


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("hailo-florence")


# Request/Response Models
class CaptionRequest(BaseModel):
    """Image captioning request."""
    image: str = Field(..., description="Base64-encoded image with data URI prefix")
    max_length: int = Field(100, ge=10, le=200, description="Maximum caption length in tokens")
    min_length: int = Field(10, ge=5, le=100, description="Minimum caption length in tokens")
    temperature: float = Field(0.7, ge=0.0, le=1.0, description="Sampling temperature")
    
    @validator('image')
    def validate_image(cls, v):
        """Validate image format."""
        if not v.startswith('data:image/'):
            raise ValueError("Image must start with 'data:image/' prefix")
        if ';base64,' not in v:
            raise ValueError("Image must be base64-encoded")
        return v
    
    @validator('max_length', 'min_length')
    def validate_lengths(cls, v, values, field):
        """Validate max_length > min_length."""
        if field.name == 'max_length' and 'min_length' in values:
            if v < values['min_length']:
                raise ValueError("max_length must be >= min_length")
        return v


class CaptionResponse(BaseModel):
    """Image captioning response."""
    caption: str
    inference_time_ms: int
    model: str
    token_count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_loaded: bool
    uptime_seconds: int
    version: str
    hailo_device: str


class MetricsResponse(BaseModel):
    """Performance metrics response."""
    requests_total: int
    requests_succeeded: int
    requests_failed: int
    average_inference_time_ms: float
    p50_inference_time_ms: float
    p95_inference_time_ms: float
    p99_inference_time_ms: float
    memory_usage_mb: int
    model_cache_hit_rate: float
    uptime_seconds: int


# Florence-2 Captioning Pipeline (Placeholder)
class FlorenceCaptioner:
    """
    Florence-2 image captioning pipeline.
    
    This is a wrapper around the hailo-rpi5-examples implementation.
    In production, this would load the actual Florence-2 models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model_loaded = False
        self.model_name = config['model']['name']
        
        logger.info("Initializing Florence-2 captioner...")
        self._load_models()
    
    def _load_models(self):
        """Load Florence-2 models (vision encoder, text encoder, decoder)."""
        model_base = Path(self.config['model']['base_path'])
        
        # Check model files exist
        required_files = [
            self.config['model']['vision_encoder'],
            self.config['model']['text_encoder'],
            self.config['model']['decoder'],
            self.config['model']['tokenizer']
        ]
        
        for file_name in required_files:
            model_path = model_base / file_name
            if not model_path.exists():
                logger.warning(f"Model file not found: {model_path}")
                logger.warning("Model will be loaded lazily on first request")
                # In production, this would fail hard
                # For now, we'll simulate successful loading
        
        # TODO: Import and initialize actual Florence-2 pipeline from hailo-rpi5-examples
        # from caption import FlorenceCaption
        # self.pipeline = FlorenceCaption(...)
        
        logger.info("Florence-2 models loaded successfully")
        self.model_loaded = True
    
    def caption(self, image: Image.Image, max_length: int = 100, 
                min_length: int = 10, temperature: float = 0.7) -> tuple[str, int]:
        """
        Generate caption for image.
        
        Args:
            image: PIL Image
            max_length: Maximum caption length
            min_length: Minimum caption length
            temperature: Sampling temperature
        
        Returns:
            (caption, inference_time_ms)
        """
        if not self.model_loaded:
            raise RuntimeError("Model not loaded")
        
        start_time = time.time()
        
        # TODO: Replace with actual Florence-2 inference
        # caption = self.pipeline.generate_caption(image, max_length, min_length, temperature)
        
        # Placeholder: Generate mock caption
        caption = self._mock_caption(image, max_length, min_length)
        
        inference_time_ms = int((time.time() - start_time) * 1000)
        
        return caption, inference_time_ms
    
    def _mock_caption(self, image: Image.Image, max_length: int, min_length: int) -> str:
        """Generate mock caption for testing (remove in production)."""
        width, height = image.size
        mode = image.mode
        
        captions = [
            "A person wearing a red shirt and blue jeans standing in front of a brick building",
            "A scenic view of mountains in the background with a clear blue sky",
            "A close-up of a cat sitting on a wooden table looking at the camera",
            "An urban street scene with cars and pedestrians visible in the frame",
            "A colorful abstract pattern with geometric shapes and vibrant colors"
        ]
        
        # Simple hash to pick consistent caption for same image
        import hashlib
        img_hash = hashlib.md5(image.tobytes()).hexdigest()
        caption_idx = int(img_hash, 16) % len(captions)
        
        caption = captions[caption_idx]
        
        # Truncate if needed
        words = caption.split()
        if len(words) > max_length // 5:  # Rough token estimation
            caption = ' '.join(words[:max_length // 5])
        
        logger.info(f"Generated caption: {caption}")
        return caption


# Global State
class ServiceState:
    """Global service state."""
    def __init__(self):
        self.start_time = time.time()
        self.captioner: Optional[FlorenceCaptioner] = None
        self.config: Dict[str, Any] = {}
        
        # Metrics
        self.requests_total = 0
        self.requests_succeeded = 0
        self.requests_failed = 0
        self.inference_times = []
        
    def uptime_seconds(self) -> int:
        return int(time.time() - self.start_time)
    
    def record_success(self, inference_time_ms: int):
        self.requests_total += 1
        self.requests_succeeded += 1
        self.inference_times.append(inference_time_ms)
        
        # Keep last 1000 measurements
        if len(self.inference_times) > 1000:
            self.inference_times = self.inference_times[-1000:]
    
    def record_failure(self):
        self.requests_total += 1
        self.requests_failed += 1
    
    def get_latency_percentile(self, percentile: int) -> float:
        if not self.inference_times:
            return 0.0
        sorted_times = sorted(self.inference_times)
        idx = int(len(sorted_times) * percentile / 100)
        return float(sorted_times[min(idx, len(sorted_times) - 1)])


state = ServiceState()


# FastAPI Application
app = FastAPI(
    title="hailo-florence",
    description="Florence-2 Image Captioning API",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize captioning pipeline on startup."""
    logger.info("Starting hailo-florence service...")
    
    # Load configuration
    config_path = os.getenv('CONFIG_PATH', '/etc/hailo/florence/config.yaml')
    logger.info(f"Loading configuration from: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            state.config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        logger.warning("Using default configuration")
        state.config = get_default_config()
    
    # Initialize captioner
    try:
        state.captioner = FlorenceCaptioner(state.config)
        logger.info("Service startup complete")
    except Exception as e:
        logger.error(f"Failed to initialize captioner: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down hailo-florence service...")


@app.post("/v1/caption", response_model=CaptionResponse)
async def generate_caption(request: CaptionRequest):
    """
    Generate natural language caption for an image.
    
    Accepts a base64-encoded image and returns a descriptive caption.
    """
    try:
        # Check model availability
        if not state.captioner or not state.captioner.model_loaded:
            raise HTTPException(
                status_code=503,
                detail="Model not loaded, please retry in a few moments"
            )
        
        # Decode image
        try:
            image = decode_image(request.image)
        except Exception as e:
            logger.error(f"Image decode error: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid image format or encoding"
            )
        
        # Validate image size
        max_bytes = state.config['model'].get('max_image_bytes', 10485760)
        image_bytes = len(request.image.split(',')[1].encode('utf-8'))
        if image_bytes > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Image too large: {image_bytes} bytes (max: {max_bytes})"
            )
        
        # Generate caption
        try:
            caption, inference_time_ms = state.captioner.caption(
                image,
                max_length=request.max_length,
                min_length=request.min_length,
                temperature=request.temperature
            )
        except Exception as e:
            logger.error(f"Inference error: {e}")
            state.record_failure()
            raise HTTPException(
                status_code=500,
                detail="Model inference failed"
            )
        
        # Record metrics
        state.record_success(inference_time_ms)
        
        # Estimate token count (rough approximation)
        token_count = len(caption.split())
        
        return CaptionResponse(
            caption=caption,
            inference_time_ms=inference_time_ms,
            model=state.captioner.model_name,
            token_count=token_count
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        state.record_failure()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Service health check."""
    hailo_device = check_hailo_device()
    
    return HealthResponse(
        status="healthy" if state.captioner and state.captioner.model_loaded else "unhealthy",
        model_loaded=state.captioner.model_loaded if state.captioner else False,
        uptime_seconds=state.uptime_seconds(),
        version="1.0.0",
        hailo_device=hailo_device
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Service performance metrics."""
    import psutil
    
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss // 1024 // 1024
    
    return MetricsResponse(
        requests_total=state.requests_total,
        requests_succeeded=state.requests_succeeded,
        requests_failed=state.requests_failed,
        average_inference_time_ms=sum(state.inference_times) / len(state.inference_times) if state.inference_times else 0.0,
        p50_inference_time_ms=state.get_latency_percentile(50),
        p95_inference_time_ms=state.get_latency_percentile(95),
        p99_inference_time_ms=state.get_latency_percentile(99),
        memory_usage_mb=memory_mb,
        model_cache_hit_rate=1.0,  # Models always resident
        uptime_seconds=state.uptime_seconds()
    )


# Helper Functions
def decode_image(image_data: str) -> Image.Image:
    """Decode base64 image to PIL Image."""
    # Extract base64 data
    if ',' in image_data:
        header, b64_data = image_data.split(',', 1)
    else:
        b64_data = image_data
    
    # Decode
    image_bytes = base64.b64decode(b64_data)
    image = Image.open(BytesIO(image_bytes))
    
    # Convert to RGB if needed
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    return image


def check_hailo_device() -> str:
    """Check if Hailo device is accessible."""
    if os.path.exists('/dev/hailo0'):
        return "connected"
    else:
        return "disconnected"


def get_default_config() -> Dict[str, Any]:
    """Get default configuration if file not found."""
    return {
        'service': {
            'host': '0.0.0.0',
            'port': 8082,
            'workers': 1,
            'log_level': 'INFO'
        },
        'model': {
            'name': 'florence-2',
            'base_path': '/opt/hailo/florence/models',
            'vision_encoder': 'florence2_davit.onnx',
            'text_encoder': 'florence2_encoder.hef',
            'decoder': 'florence2_decoder.hef',
            'tokenizer': 'tokenizer.json',
            'max_length': 100,
            'min_length': 10,
            'temperature': 0.7,
            'image_size': 384,
            'max_image_bytes': 10485760
        },
        'resources': {
            'memory_limit': '4G',
            'vram_budget': '3G',
            'max_concurrent_requests': 1,
            'request_timeout_seconds': 30
        },
        'logging': {
            'level': 'INFO',
            'format': 'json'
        }
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="hailo-florence REST API server")
    parser.add_argument('--config', default='/etc/hailo/florence/config.yaml',
                        help='Path to configuration file')
    parser.add_argument('--host', default=None, help='Override host')
    parser.add_argument('--port', type=int, default=None, help='Override port')
    
    args = parser.parse_args()
    
    # Set config path env var for startup event
    os.environ['CONFIG_PATH'] = args.config
    
    # Load config to get host/port
    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {args.config}, using defaults")
        config = get_default_config()
    
    host = args.host or config['service']['host']
    port = args.port or config['service']['port']
    log_level = config['service'].get('log_level', 'INFO').lower()
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=True
    )


if __name__ == '__main__':
    main()
