#!/usr/bin/env python3
"""
Hailo OCR Server

Exposes PaddleOCR via REST API on configurable port.
-"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import web
from PIL import Image

try:
    from paddleocr import PaddleOCR
except ImportError:
    print("ERROR: PaddleOCR not installed. Install with: pip install paddleocr", file=sys.stderr)
    sys.exit(1)

# Setup logging
logging.basicConfig(
    format="[hailo-ocr] %(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Global state
ocr_instance = None
config = {}
cache = {}
cache_lock = asyncio.Lock()
start_time = time.time()
model_load_time = None


class OCRServer:
    """Async OCR server wrapper around PaddleOCR."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()
        self.ocr = None
        self.load_count = 0
        logger.info(f"OCRServer initialized with config: {self.config_path}")

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate JSON configuration."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            return cfg
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON config: {e}")
            sys.exit(1)

    def load_models(self):
        """Lazy-load PaddleOCR models on first use."""
        global model_load_time
        
        if self.ocr is not None:
            return
        
        logger.info("Loading PaddleOCR models...")
        start = time.time()
        
        languages = self.config.get('ocr', {}).get('languages', ['en'])
        lang = ",".join(languages)
        
        try:
            self.ocr = PaddleOCR(
                use_gpu=self.config.get('ocr', {}).get('use_gpu', False),
                lang=lang,
                det_model_dir=None,  # Use default cache
                rec_model_dir=None,
                verbose=False
            )
            elapsed = time.time() - start
            model_load_time = elapsed
            logger.info(f"Models loaded successfully in {elapsed:.1f}s")
            self.load_count += 1
        except Exception as e:
            logger.error(f"Failed to load models: {e}", exc_info=True)
            raise

    def get_health(self) -> Dict[str, Any]:
        """Return health status."""
        uptime = time.time() - start_time
        return {
            "status": "ok",
            "models_loaded": self.ocr is not None,
            "detection_model": "ch_PP-OCRv3_det_infer",
            "recognition_model": "ch_PP-OCRv3_rec_infer",
            "memory_usage_mb": self._get_memory_usage(),
            "cache_size_mb": sum(len(v) for v in cache.values()) // (1024 * 1024),
            "uptime_seconds": int(uptime),
            "model_loads": self.load_count
        }

    def _get_memory_usage(self) -> int:
        """Get process memory usage in MB."""
        try:
            with open(f"/proc/{os.getpid()}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) // 1024  # Convert KB to MB
        except FileNotFoundError:
            pass
        return 0

    def _load_image_from_uri(self, image_uri: str) -> Optional[Image.Image]:
        """Load image from various URI formats."""
        try:
            # Handle data URI (base64)
            if image_uri.startswith("data:"):
                import base64
                parts = image_uri.split(",", 1)
                if len(parts) != 2:
                    return None
                b64_data = base64.b64decode(parts[1])
                return Image.open(self._bytes_to_file(b64_data))
            
            # Handle file URI
            elif image_uri.startswith("file://"):
                path = image_uri.replace("file://", "")
                return Image.open(path)
            
            # Handle HTTP/HTTPS (not implemented; would need aiohttp.ClientSession)
            else:
                logger.warning(f"HTTP image loading not yet implemented: {image_uri}")
                return None
        except Exception as e:
            logger.error(f"Error loading image: {e}")
            return None

    @staticmethod
    def _bytes_to_file(data: bytes):
        """Convert bytes to file-like object."""
        import io
        return io.BytesIO(data)

    def extract_ocr(self, image_bytes: bytes, languages: Optional[list] = None, **kwargs) -> Dict[str, Any]:
        """Run OCR on image bytes."""
        # Lazy-load models on first use
        if self.ocr is None:
            self.load_models()
        
        det_threshold = kwargs.get('det_threshold', self.config['ocr']['det_threshold'])
        rec_threshold = kwargs.get('rec_threshold', self.config['ocr']['rec_threshold'])
        enable_recognition = kwargs.get('enable_recognition', self.config['ocr']['enable_recognition'])
        
        try:
            # Save to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            
            try:
                start = time.time()
                # Run OCR
                results = self.ocr.ocr(tmp_path, cls=enable_recognition)
                elapsed = time.time() - start
                
                # Transform results to API format
                regions = []
                all_text = []
                
                if results:
                    for line in results:
                        for word_info in line:
                            bbox, text, confidence = word_info
                            regions.append({
                                "text": text,
                                "confidence": float(confidence),
                                "bbox": [[int(p[0]), int(p[1])] for p in bbox],
                                "type": "text"
                            })
                            all_text.append(text)
                
                return {
                    "success": True,
                    "text": " ".join(all_text),
                    "regions": regions,
                    "languages_detected": languages or ['en'],
                    "statistics": {
                        "total_regions": len(regions),
                        "average_confidence": sum(r['confidence'] for r in regions) / len(regions) if regions else 0
                    },
                    "performance": {
                        "detection_time_ms": int(elapsed * 1000),
                        "recognition_time_ms": 0,
                        "total_time_ms": int(elapsed * 1000)
                    }
                }
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


# Routes
async def handle_health(request):
    """GET /health"""
    if ocr_instance is None:
        return web.json_response({"error": "Server not initialized"}, status=500)
    
    return web.json_response(ocr_instance.get_health())


async def handle_ready(request):
    """GET /health/ready"""
    if ocr_instance.ocr is None:
        return web.json_response(
            {"ready": False, "reason": "models_loading"},
            status=503
        )
    return web.json_response({"ready": True})


async def handle_models(request):
    """GET /models"""
    languages = config.get('ocr', {}).get('languages', ['en'])
    data = []
    for lang in languages:
        data.append({
            "id": lang,
            "name": lang,
            "status": "loaded" if ocr_instance.ocr else "available"
        })
    
    return web.json_response({
        "data": data,
        "object": "list"
    })


async def handle_extract(request):
    """POST /v1/ocr/extract"""
    try:
        payload = await request.json()
    except Exception as e:
        return web.json_response(
            {"success": False, "error": str(e)},
            status=400
        )
    
    image_uri = payload.get('image')
    if not image_uri:
        return web.json_response(
            {"success": False, "error": "Missing 'image' parameter"},
            status=400
        )
    
    # Load image
    img = ocr_instance._load_image_from_uri(image_uri)
    if img is None:
        return web.json_response(
            {"success": False, "error": "Failed to load image"},
            status=400
        )
    
    # Convert to bytes
    import io
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG', quality=config['processing']['jpeg_quality'])
    img_bytes = img_bytes.getvalue()
    
    # Run OCR
    languages = payload.get('languages', config['ocr']['languages'])
    cache_key = md5(img_bytes).hexdigest() if payload.get('cache_result') else None
    
    # Check cache
    if cache_key and cache_key in cache:
        logger.info(f"Cache hit for {cache_key}")
        result = cache[cache_key]
        result['cached'] = True
        return web.json_response(result)
    
    # Run extraction
    result = ocr_instance.extract_ocr(
        img_bytes,
        languages=languages,
        det_threshold=payload.get('det_threshold'),
        rec_threshold=payload.get('rec_threshold'),
        enable_recognition=payload.get('enable_recognition', True)
    )
    
    # Cache if requested
    if cache_key and result.get('success'):
        async with cache_lock:
            cache[cache_key] = result.copy()
    
    result['cached'] = False
    return web.json_response(result)


async def handle_batch(request):
    """POST /v1/ocr/batch"""
    try:
        payload = await request.json()
    except Exception as e:
        return web.json_response(
            {"success": False, "error": str(e)},
            status=400
        )
    
    images = payload.get('images', [])
    if not images:
        return web.json_response(
            {"success": False, "error": "Missing 'images' parameter"},
            status=400
        )
    
    results = []
    for image_uri in images:
        img = ocr_instance._load_image_from_uri(image_uri)
        if img is None:
            results.append({
                "image_url": image_uri,
                "status": "error",
                "error": "Failed to load image"
            })
            continue
        
        import io
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG', quality=config['processing']['jpeg_quality'])
        img_bytes = img_bytes.getvalue()
        
        result = ocr_instance.extract_ocr(img_bytes)
        result['image_url'] = image_uri
        result['status'] = 'success' if result.get('success') else 'error'
        results.append(result)
    
    return web.json_response({
        "success": True,
        "batch_id": f"batch-{int(time.time())}",
        "images_processed": len(images),
        "results": results
    })


async def handle_cache_clear(request):
    """DELETE /cache"""
    async with cache_lock:
        count = len(cache)
        cache.clear()
    
    return web.json_response({
        "success": True,
        "cache_cleared": True,
        "items_removed": count
    })


async def handle_cache_stats(request):
    """GET /cache/stats"""
    return web.json_response({
        "enabled": config['processing']['enable_caching'],
        "items_cached": len(cache),
        "memory_used_mb": sum(len(v) for v in cache.values()) // (1024 * 1024),
        "memory_limit_mb": config['processing']['max_cache_size_mb'],
        "ttl_seconds": config['processing']['cache_ttl_seconds'],
        "hit_rate": 0.0
    })


async def start_server():
    """Start the aiohttp server."""
    global ocr_instance, config
    
    config_path = os.getenv(
        'OCR_CONFIG_PATH',
        '/etc/xdg/hailo-ocr/hailo-ocr.json'
    )
    
    # Load configuration
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)
    
    # Create OCR instance
    ocr_instance = OCRServer(config_path)
    
    # Create web app
    app = web.Application()
    
    # Register routes
    app.router.add_get('/health', handle_health)
    app.router.add_get('/health/ready', handle_ready)
    app.router.add_get('/models', handle_models)
    app.router.add_post('/v1/ocr/extract', handle_extract)
    app.router.add_post('/v1/ocr/batch', handle_batch)
    app.router.add_delete('/cache', handle_cache_clear)
    app.router.add_get('/cache/stats', handle_cache_stats)
    
    # Setup graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(shutdown(app))
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start server
    host = config['server']['host']
    port = config['server']['port']
    
    logger.info(f"Starting server on {host}:{port}")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"Server ready at http://{host}:{port}")


async def shutdown(app):
    """Graceful shutdown."""
    logger.info("Shutting down...")
    sys.exit(0)


def main():
    """Main entry point."""
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
