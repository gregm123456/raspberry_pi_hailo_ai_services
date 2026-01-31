#!/usr/bin/env python3
"""
Hailo Pose Service - YOLOv8 Pose Estimation on Hailo-10H

REST API server exposing pose estimation inference.
Detects human keypoints and skeleton connections in COCO format.
"""

import asyncio
import base64
import json
import logging
import os
import sys
from datetime import datetime
from io import BytesIO
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
logger = logging.getLogger('hailo-pose')

# Configuration paths
XDG_CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', '/etc/xdg')
CONFIG_JSON = os.path.join(XDG_CONFIG_HOME, 'hailo-pose', 'hailo-pose.json')

# COCO keypoint names (17 keypoints)
COCO_KEYPOINTS = [
    'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
    'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
    'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
    'left_knee', 'right_knee', 'left_ankle', 'right_ankle'
]

# COCO skeleton connections (pairs of keypoint indices)
COCO_SKELETON = [
    [16, 14], [14, 12], [17, 15], [15, 13], [12, 13],  # legs
    [6, 12], [7, 13], [6, 7],  # torso
    [6, 8], [7, 9], [8, 10], [9, 11],  # arms
    [2, 3], [1, 2], [1, 3], [2, 4], [3, 5], [4, 6], [5, 7]  # head
]

class PoseServiceConfig:
    """Configuration management."""
    
    def __init__(self):
        self.server_host = "0.0.0.0"
        self.server_port = 11436
        self.model_name = "yolov8s-pose"
        self.keep_alive = -1
        
        self.confidence_threshold = 0.5
        self.iou_threshold = 0.45
        self.max_detections = 10
        self.input_size = [640, 640]
        
        self.keypoint_threshold = 0.3
        self.skeleton_connections = True
        
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
            
            # Parse inference config
            inference = config.get('inference', {})
            self.confidence_threshold = inference.get('confidence_threshold', self.confidence_threshold)
            self.iou_threshold = inference.get('iou_threshold', self.iou_threshold)
            self.max_detections = inference.get('max_detections', self.max_detections)
            self.input_size = inference.get('input_size', self.input_size)
            
            # Parse pose config
            pose = config.get('pose', {})
            self.keypoint_threshold = pose.get('keypoint_threshold', self.keypoint_threshold)
            self.skeleton_connections = pose.get('skeleton_connections', self.skeleton_connections)
            
            logger.info(f"Loaded config from {CONFIG_JSON}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

class PoseService:
    """Pose estimation service with model lifecycle management."""
    
    def __init__(self, config: PoseServiceConfig):
        self.config = config
        self.model = None
        self.is_loaded = False
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
    
    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing model: {self.config.model_name}")
        
        try:
            # TODO: Implement HailoRT YOLOv8-pose model loading
            # This is a placeholder for the actual Hailo integration
            # In production, this would:
            # 1. Load the HEF model via HailoRT SDK
            # 2. Initialize NPU device
            # 3. Verify device memory and model compatibility
            # 4. Pre-allocate inference buffers
            
            logger.info("Model initialization placeholder (HailoRT YOLOv8-pose)")
            self.is_loaded = True
            
        except Exception as e:
            logger.error(f"Model initialization failed: {e}")
            raise
    
    async def detect_poses(
        self,
        image_data: bytes,
        confidence_threshold: float = None,
        iou_threshold: float = None,
        max_detections: int = None,
        keypoint_threshold: float = None
    ) -> Dict[str, Any]:
        """Detect human poses in image."""
        
        if not self.is_loaded:
            raise RuntimeError("Model not loaded")
        
        # Use config defaults if not provided
        confidence_threshold = confidence_threshold or self.config.confidence_threshold
        iou_threshold = iou_threshold or self.config.iou_threshold
        max_detections = max_detections or self.config.max_detections
        keypoint_threshold = keypoint_threshold or self.config.keypoint_threshold
        
        try:
            # TODO: Implement actual pose estimation inference
            # This is a placeholder for HailoRT inference
            # In production, this would:
            # 1. Decode image bytes
            # 2. Preprocess (resize, normalize) to input_size
            # 3. Run inference on NPU via HailoRT
            # 4. Post-process outputs:
            #    - Extract bounding boxes
            #    - Extract keypoint coordinates (x, y, confidence)
            #    - Apply NMS (Non-Maximum Suppression)
            #    - Filter by confidence threshold
            # 5. Format results in COCO keypoint format
            
            # Placeholder response
            poses = [
                {
                    "person_id": 0,
                    "bbox": {"x": 100, "y": 50, "width": 200, "height": 400},
                    "bbox_confidence": 0.92,
                    "keypoints": [
                        {"name": name, "x": 150 + i * 10, "y": 100 + i * 20, "confidence": 0.85}
                        for i, name in enumerate(COCO_KEYPOINTS)
                    ]
                }
            ]
            
            if self.config.skeleton_connections:
                for pose in poses:
                    pose["skeleton"] = [
                        {
                            "from": COCO_KEYPOINTS[conn[0] - 1],
                            "to": COCO_KEYPOINTS[conn[1] - 1],
                            "from_index": conn[0] - 1,
                            "to_index": conn[1] - 1
                        }
                        for conn in COCO_SKELETON
                    ]
            
            response = {
                "poses": poses,
                "count": len(poses),
                "inference_time_ms": 45,
                "image_size": {"width": 640, "height": 480}
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
    
    def __init__(self, service: PoseService):
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
                    "owned_by": "hailo",
                    "task": "pose-estimation"
                }
            ],
            "object": "list"
        })
    
    async def detect(self, request: web.Request) -> web.Response:
        """POST /v1/pose/detect - Detect poses in image."""
        
        try:
            # Handle both multipart/form-data and JSON
            content_type = request.headers.get('Content-Type', '')
            
            if 'multipart/form-data' in content_type:
                # Read multipart form
                reader = await request.multipart()
                image_data = None
                params = {}
                
                async for field in reader:
                    if field.name == 'image':
                        image_data = await field.read()
                    elif field.name in ['confidence_threshold', 'iou_threshold', 'keypoint_threshold']:
                        params[field.name] = float(await field.text())
                    elif field.name == 'max_detections':
                        params[field.name] = int(await field.text())
                
                if not image_data:
                    return web.json_response(
                        {"error": {"message": "Missing 'image' field", "type": "invalid_request_error"}},
                        status=400
                    )
            
            else:
                # JSON payload with base64 image
                try:
                    payload = await request.json()
                except Exception as e:
                    return web.json_response(
                        {"error": {"message": f"Invalid JSON: {e}", "type": "invalid_request_error"}},
                        status=400
                    )
                
                image_b64 = payload.get("image")
                if not image_b64:
                    return web.json_response(
                        {"error": {"message": "Missing 'image' field", "type": "invalid_request_error"}},
                        status=400
                    )
                
                # Decode base64 (handle data URI if present)
                if image_b64.startswith('data:'):
                    image_b64 = image_b64.split(',', 1)[1]
                
                try:
                    image_data = base64.b64decode(image_b64)
                except Exception as e:
                    return web.json_response(
                        {"error": {"message": f"Invalid base64: {e}", "type": "invalid_request_error"}},
                        status=400
                    )
                
                params = {
                    k: payload.get(k) for k in 
                    ['confidence_threshold', 'iou_threshold', 'max_detections', 'keypoint_threshold']
                    if k in payload
                }
            
            # Run inference
            try:
                result = await self.service.detect_poses(image_data, **params)
                return web.json_response(result)
                
            except Exception as e:
                logger.error(f"Inference error: {e}")
                return web.json_response(
                    {"error": {"message": str(e), "type": "internal_error"}},
                    status=500
                )
        
        except Exception as e:
            logger.error(f"Request handling error: {e}")
            return web.json_response(
                {"error": {"message": str(e), "type": "internal_error"}},
                status=500
            )

async def create_app(service: PoseService) -> web.Application:
    """Create aiohttp application."""
    handler = APIHandler(service)
    app = web.Application()
    
    # Routes
    app.router.add_get('/health', handler.health)
    app.router.add_get('/health/ready', handler.health_ready)
    app.router.add_get('/v1/models', handler.list_models)
    app.router.add_post('/v1/pose/detect', handler.detect)
    
    return app

async def main():
    """Main entry point."""
    try:
        # Load configuration
        config = PoseServiceConfig()
        logger.info(f"Hailo Pose Service starting")
        logger.info(f"Server: {config.server_host}:{config.server_port}")
        logger.info(f"Model: {config.model_name}")
        
        # Initialize service
        service = PoseService(config)
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
