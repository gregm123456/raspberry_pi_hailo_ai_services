#!/usr/bin/env python3
"""
Hailo-10H Accelerated OCR Server

Exposes Hailo-accelerated OCR via REST API.
Uses hailo-apps infrastructure for NPU inference.
"""

import asyncio
import base64
import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import cv2
import numpy as np
from aiohttp import web
from PIL import Image

# Import device manager client
from device_client import HailoDeviceClient

# Add vendored hailo-apps to path
VENDOR_DIR = Path("/opt/hailo-ocr/vendor/hailo-apps")
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))
    # Also add the paddle_ocr directory to handle relative imports
    paddle_ocr_dir = VENDOR_DIR / "hailo_apps/python/standalone_apps/paddle_ocr"
    if paddle_ocr_dir.exists():
        sys.path.insert(0, str(paddle_ocr_dir))

try:
    from hailo_apps.python.standalone_apps.paddle_ocr.paddle_ocr_utils import (
        det_postprocess,
        resize_with_padding,
        ocr_eval_postprocess,
        map_bbox_to_original_image,
        OcrCorrector
    )
except ImportError:
    # Fallback for local development if not vendored yet
    try:
        from hailo_apps.python.standalone_apps.paddle_ocr.paddle_ocr_utils import (
            det_postprocess,
            resize_with_padding,
            ocr_eval_postprocess,
            map_bbox_to_original_image
        )
        OcrCorrector = None  # Not available
    except ImportError as e:
        # We don't exit here because the service might be starting up before venv/vendor is ready during install
        pass


def encode_tensor(array: np.ndarray) -> Dict[str, Any]:
    """Encode numpy array as base64 for device manager."""
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }


def decode_tensor(payload: Dict[str, Any]) -> np.ndarray:
    """Decode base64 tensor from device manager."""
    dtype = payload.get("dtype")
    shape = payload.get("shape")
    data_b64 = payload.get("data_b64")

    if not dtype or shape is None or not data_b64:
        raise ValueError("tensor must include dtype, shape, and data_b64")

    raw = base64.b64decode(data_b64)
    array = np.frombuffer(raw, dtype=np.dtype(dtype))
    return array.reshape(shape).copy()

# Setup logging
logging.basicConfig(
    format="[hailo-ocr] %(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Global state
ocr_service = None
config = {}
cache = {}
cache_lock = asyncio.Lock()
start_time = time.time()

class HailoOCRService:
    """Async OCR service using Hailo-10H NPU via device manager."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client: Optional[HailoDeviceClient] = None
        self.detection_model_path: Optional[str] = None
        self.recognition_model_paths: Dict[str, str] = {}  # lang -> path
        self.batch_sizes: Dict[str, int] = {}  # lang -> batch_size
        self.detection_input_shape: Optional[Tuple[int, int, int]] = None
        self.ocr_corrector = None
        self.load_count = 0
        self.device = config.get('hailo_models', {}).get('device', '/dev/hailo0')
        self.is_loaded = False
        
    async def initialize(self):
        """Initialize models via device manager."""
        logger.info("Initializing Hailo OCR Service...")
        start = time.time()
        
        try:
            # 1. Resolve model paths
            self.detection_model_path = self._resolve_model_path(
                self.config['hailo_models']['detection_hef']
            )
            logger.info(f"Detection model: {self.detection_model_path}")

            rec_configs = self.config['hailo_models'].get('recognition_hefs', {})
            batch_size_rec = self.config['hailo_models'].get('batch_size_rec', 8)
            
            for lang, hef_name in rec_configs.items():
                hef_path = self._resolve_model_path(hef_name)
                if os.path.exists(hef_path):
                    logger.info(f"Recognition model [{lang}]: {hef_path}")
                    self.recognition_model_paths[lang] = hef_path
                    self.batch_sizes[lang] = batch_size_rec
                else:
                    logger.warning(f"Recognition model for {lang} not found at {hef_path}")

            # 2. Connect to device manager
            self.client = HailoDeviceClient()
            await self.client.connect()
            logger.info("Connected to device manager")

            # 3. Load OCR models via device manager
            model_params = {
                "detection_hef_path": self.detection_model_path,
                "recognition_hefs": self.recognition_model_paths,
                "batch_sizes": self.batch_sizes,
            }

            load_response = await self.client.load_model(
                self.detection_model_path,  # Use detection path as primary key
                model_type="ocr",
                model_params=model_params
            )
            model_info = load_response.get("model_info", {})
            shape = model_info.get("detection_input_shape")
            if shape and len(shape) == 3:
                self.detection_input_shape = tuple(shape)
            else:
                self.detection_input_shape = (640, 640, 3)
            logger.info("Models loaded via device manager")

            # 4. Initialize Corrector (optional)
            if OcrCorrector and self.config.get('ocr', {}).get('use_corrector', False):
                dict_path = self.config.get('ocr', {}).get('dictionary_path', 'frequency_dictionary_en_82_765.txt')
                try:
                    self.ocr_corrector = OcrCorrector(dict_path)
                except Exception as e:
                    logger.warning(f"Failed to load OcrCorrector: {e}")

            self.is_loaded = True
            self.load_count += 1
            elapsed = time.time() - start
            logger.info(f"Hailo OCR Service ready in {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise

    def _resolve_model_path(self, model_name: str) -> str:
        """Resolve model path using standard locations."""
        if os.path.isabs(model_name):
            return model_name
        
        search_paths = [
            Path(self.config.get('hailo_models', {}).get('models_root', '/var/lib/hailo-ocr/resources/models/hailo10h')),
            VENDOR_DIR / "local_resources/models/hailo10h",
            Path("/var/lib/hailo-ocr/resources/models/hailo10h")
        ]
        
        for p in search_paths:
            full_path = p / model_name
            if full_path.exists():
                return str(full_path)
        
        return model_name # Fallback

    async def run_detection(self, image_np: np.ndarray) -> Tuple[List[np.ndarray], List[List[int]]]:
        """Run detection via device manager and return crops and boxes."""
        h, w, _ = self.detection_input_shape
        processed = resize_with_padding(image_np, target_height=h, target_width=w)
        
        # Run inference via device manager
        response = await self.client.infer(
            self.detection_model_path,
            {
                "mode": "detection",
                "image": encode_tensor(processed),
            },
            model_type="ocr",
        )
        
        # Decode result
        raw_result = decode_tensor(response["result"])
        
        # Post-process detection
        crops, boxes = det_postprocess(raw_result, image_np, h, w)
        return crops, boxes

    async def run_recognition(self, crops: List[np.ndarray], lang: str) -> List[Tuple[str, float]]:
        """Run recognition on crops via device manager (batching handled by device manager)."""
        if lang not in self.recognition_model_paths:
            lang = 'en' # Default
        
        if lang not in self.recognition_model_paths:
            raise ValueError(f"No recognition model loaded for language: {lang}")
            
        batch_size = self.batch_sizes.get(lang, self.config['hailo_models'].get('batch_size_rec', 8))
        
        # Prepare all resized crops
        resized_crops = [resize_with_padding(c) for c in crops]
        
        # Encode crops for device manager
        encoded_crops = [encode_tensor(crop) for crop in resized_crops]
        
        # Run recognition via device manager (batching handled internally)
        response = await self.client.infer(
            self.detection_model_path,  # Use detection path as model key
            {
                "mode": "recognition",
                "language": lang,
                "crops": encoded_crops,
                "batch_size": batch_size,
            },
            model_type="ocr",
        )
        
        # Decode batch results
        batch_raw_results = response["result"]  # List of encoded tensors
        results = []
        for raw_tensor in batch_raw_results:
            raw_result = decode_tensor(raw_tensor)
            decoded = ocr_eval_postprocess(raw_result)[0]
            results.append(decoded)
                
        return results

    async def extract_ocr(self, image_np: np.ndarray, languages: List[str]) -> Dict[str, Any]:
        """Perform full OCR pipeline."""
        start_total = time.time()
        
        # 1. Detection
        start_det = time.time()
        crops, boxes = await self.run_detection(image_np)
        det_time = time.time() - start_det
        
        if not crops:
            return {
                "success": True,
                "text": "",
                "regions": [],
                "performance": {
                    "detection_time_ms": int(det_time * 1000),
                    "recognition_time_ms": 0,
                    "total_time_ms": int((time.time() - start_total) * 1000)
                }
            }

        # Sort boxes by y then x to ensure logical reading order (line-based)
        # We group nearby y-coordinates into the same "line" using a threshold
        line_height_threshold = 20 
        combined = sorted(zip(crops, boxes), key=lambda x: (x[1][1] // line_height_threshold, x[1][0]))
        crops, boxes = zip(*combined)
        crops = list(crops)
        boxes = list(boxes)
            
        # 2. Recognition (per requested language)
        start_rec = time.time()
        all_results = []
        
        # For simplicity, we use the first requested language for all regions
        primary_lang = languages[0] if languages else 'en'
        
        rec_results = await self.run_recognition(crops, primary_lang)
        rec_time = time.time() - start_rec
        
        # 3. Format results
        regions = []
        full_text_list = []
        
        for (text, conf), box in zip(rec_results, boxes):
            if self.ocr_corrector:
                text = self.ocr_corrector.correct_text(text)
            
            regions.append({
                "text": text,
                "confidence": float(conf),
                "bbox": [[box[0], box[1]], [box[0]+box[2], box[1]], [box[0]+box[2], box[1]+box[3]], [box[0], box[1]+box[3]]],
                "type": "text"
            })
            if text.strip():
                full_text_list.append(text)
        
        total_time = time.time() - start_total
        
        return {
            "success": True,
            "text": " ".join(full_text_list),
            "regions": regions,
            "languages_detected": [primary_lang],
            "statistics": {
                "total_regions": len(regions),
                "average_confidence": sum(r['confidence'] for r in regions) / len(regions) if regions else 0
            },
            "performance": {
                "detection_time_ms": int(det_time * 1000),
                "recognition_time_ms": int(rec_time * 1000),
                "total_time_ms": int(total_time * 1000)
            },
            "hailo_info": {
                "device": self.device,
                "detection_model": self.config['hailo_models']['detection_hef'],
                "recognition_model": self.config['hailo_models']['recognition_hefs'].get(primary_lang)
            }
        }

    def get_health(self) -> Dict[str, Any]:
        """Return health status."""
        uptime = time.time() - start_time
        return {
            "status": "ok",
            "models_loaded": self.is_loaded,
            "languages_supported": list(self.recognition_model_paths.keys()),
            "memory_usage_mb": self._get_memory_usage(),
            "uptime_seconds": int(uptime),
            "model_loads": self.load_count,
            "hailo_device": self.device
        }

    def _get_memory_usage(self) -> int:
        """Get process memory usage in MB."""
        try:
            with open(f"/proc/{os.getpid()}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) // 1024
        except FileNotFoundError:
            pass
        return 0

# Routes
async def handle_health(request):
    """GET /health"""
    if ocr_service is None:
        return web.json_response({"error": "Service not initialized"}, status=500)
    return web.json_response(ocr_service.get_health())

async def handle_ready(request):
    """GET /health/ready"""
    if not ocr_service or not ocr_service.is_loaded:
        return web.json_response({"ready": False, "reason": "models_loading"}, status=503)
    return web.json_response({"ready": True})

async def handle_models(request):
    """GET /models"""
    data = []
    # Detection
    data.append({
        "id": "detection",
        "name": config['hailo_models']['detection_hef'],
        "type": "detection",
        "status": "loaded" if ocr_service and ocr_service.is_loaded else "pending"
    })
    # Recognition
    for lang, hef in config['hailo_models'].get('recognition_hefs', {}).items():
        data.append({
            "id": f"recognition_{lang}",
            "name": hef,
            "type": "recognition",
            "language": lang,
            "status": "loaded" if ocr_service and lang in ocr_service.recognition_model_paths else "not_found"
        })
    
    return web.json_response({"data": data, "object": "list"})

async def handle_extract(request):
    """POST /v1/ocr/extract"""
    try:
        payload = await request.json()
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    
    image_uri = payload.get('image')
    if not image_uri:
        return web.json_response({"success": False, "error": "Missing 'image' parameter"}, status=400)
    
    # Load image
    img_np = await load_image(image_uri)
    if img_np is None:
        return web.json_response({"success": False, "error": "Failed to load image"}, status=400)
    
    # Run OCR
    languages = payload.get('languages', config['ocr']['languages'])
    
    result = await ocr_service.extract_ocr(img_np, languages=languages)
    return web.json_response(result)

async def load_image(uri: str) -> Optional[np.ndarray]:
    """Load image and return as NumPy array (RGB)."""
    try:
        if uri.startswith("data:"):
            import base64
            parts = uri.split(",", 1)
            b64_data = base64.b64decode(parts[1])
            nparr = np.frombuffer(b64_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        elif uri.startswith("file://"):
            path = uri.replace("file://", "")
            img = cv2.imread(path)
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return None
    except Exception as e:
        logger.error(f"Error loading image: {e}")
        return None

async def start_server():
    """Start the aiohttp server."""
    global ocr_service, config
    
    config_path = os.getenv('OCR_CONFIG_PATH', '/etc/xdg/hailo-ocr/hailo-ocr.json')
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config {config_path}: {e}")
        sys.exit(1)
        
    ocr_service = HailoOCRService(config)
    await ocr_service.initialize()
    
    app = web.Application(client_max_size=1024**2 * 10) # 10MB limit
    app.router.add_get('/health', handle_health)
    app.router.add_get('/health/ready', handle_ready)
    app.router.add_get('/models', handle_models)
    app.router.add_post('/v1/ocr/extract', handle_extract)
    
    # Graceful shutdown
    async def on_shutdown(app):
        logger.info("Disconnecting from device manager...")
        if ocr_service and ocr_service.client:
            await ocr_service.client.disconnect()

    app.on_shutdown.append(on_shutdown)
    
    host = config['server']['host']
    port = config['server']['port']
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"Server ready at http://{host}:{port}")
    
    # Keep running
    while True:
        await asyncio.sleep(3600)

def main():
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
