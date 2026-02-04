#!/usr/bin/env python3
"""Hailo Pose Service - YOLOv8 pose estimation on Hailo-10H."""

import asyncio
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from aiohttp import web
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip3 install aiohttp pillow numpy")
    sys.exit(1)

# Add vendored hailo-apps to path if present
VENDOR_DIR = Path("/opt/hailo-pose/vendor/hailo-apps")
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

try:
    from hailo_apps.python.core.common.hailo_inference import HailoInfer
    from hailo_apps.python.core.common.core import resolve_hef_path
    from hailo_apps.python.core.common.defines import (
        HAILO10H_ARCH,
        POSE_ESTIMATION_PIPELINE,
    )
    from hailo_apps.python.core.common.toolbox import default_preprocess
    from hailo_apps.python.standalone_apps.pose_estimation.pose_estimation_utils import (
        PoseEstPostProcessing,
    )
except ImportError as e:
    print(f"Error: hailo-apps not found: {e}")
    print("Ensure hailo-apps is installed or vendored in /opt/hailo-pose/vendor")
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
        self.model_name = "yolov8s_pose"
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
        self.infer = None
        self.is_loaded = False
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
        self.model_input_shape = None
        self.infer_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing model: {self.config.model_name}")

        try:
            hef_path = resolve_hef_path(
                hef_path=self.config.model_name,
                app_name=POSE_ESTIMATION_PIPELINE,
                arch=HAILO10H_ARCH,
            )

            if hef_path is None:
                raise RuntimeError("Failed to resolve HEF model path")

            logger.info(f"Using HEF: {hef_path}")

            start = time.time()
            self.infer = HailoInfer(str(hef_path), batch_size=1, output_type="FLOAT32")
            self.model_input_shape = self.infer.get_input_shape()
            self.load_time_ms = int((time.time() - start) * 1000)
            self.is_loaded = True
            logger.info(f"Model loaded in {self.load_time_ms} ms")
        except Exception as e:
            logger.error(f"Model initialization failed: {e}")
            raise

    def _build_post_processor(
        self,
        confidence_threshold: float,
        iou_threshold: float,
        max_detections: int,
    ) -> PoseEstPostProcessing:
        return PoseEstPostProcessing(
            max_detections=max_detections,
            score_threshold=confidence_threshold,
            nms_iou_thresh=iou_threshold,
            regression_length=15,
            strides=[8, 16, 32],
        )

    async def _run_inference(self, input_tensor: np.ndarray) -> Dict[str, np.ndarray]:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def callback(completion_info, bindings_list):
            if completion_info.exception:
                loop.call_soon_threadsafe(future.set_exception, completion_info.exception)
                return

            bindings = bindings_list[0]
            if len(bindings._output_names) == 1:
                result = bindings.output().get_buffer()
            else:
                result = {
                    name: np.expand_dims(bindings.output(name).get_buffer(), axis=0)
                    for name in bindings._output_names
                }
            loop.call_soon_threadsafe(future.set_result, result)

        self.infer.run([input_tensor], callback)
        return await future

    async def detect_poses(
        self,
        image_data: bytes,
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
        max_detections: Optional[int] = None,
        keypoint_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Detect human poses in image."""

        if not self.is_loaded or not self.infer:
            raise RuntimeError("Model not loaded")

        confidence_threshold = (
            confidence_threshold if confidence_threshold is not None else self.config.confidence_threshold
        )
        iou_threshold = iou_threshold if iou_threshold is not None else self.config.iou_threshold
        max_detections = max_detections if max_detections is not None else self.config.max_detections
        keypoint_threshold = (
            keypoint_threshold if keypoint_threshold is not None else self.config.keypoint_threshold
        )

        try:
            image = Image.open(BytesIO(image_data)).convert("RGB")
            image_np = np.array(image)
        except Exception as e:
            raise ValueError(f"Failed to decode image: {e}")

        orig_h, orig_w = image_np.shape[:2]
        model_h, model_w, _ = self.model_input_shape

        preprocessed = default_preprocess(image_np, model_w, model_h)

        start = time.time()
        async with self.infer_lock:
            raw = await self._run_inference(preprocessed)
        inference_time_ms = int((time.time() - start) * 1000)

        post_processor = self._build_post_processor(
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            max_detections=max_detections,
        )

        results = post_processor.post_process(raw, model_h, model_w, class_num=1)
        bboxes = results["bboxes"][0]
        keypoints = results["keypoints"][0]
        joint_scores = results["joint_scores"][0]
        scores = results["scores"][0]

        poses = []
        for idx in range(min(len(bboxes), max_detections)):
            if scores[idx][0] < confidence_threshold:
                continue

            bbox = post_processor.map_box_to_original_coords(
                bboxes[idx].tolist(),
                orig_w,
                orig_h,
                model_w,
                model_h,
            )
            xmin, ymin, xmax, ymax = bbox

            mapped_keypoints = post_processor.map_keypoints_to_original_coords(
                keypoints[idx].copy(),
                orig_w,
                orig_h,
                model_w,
                model_h,
            )

            kp_scores = joint_scores[idx].reshape(-1)
            pose_keypoints = []
            for kp_index, name in enumerate(COCO_KEYPOINTS):
                pose_keypoints.append(
                    {
                        "name": name,
                        "x": int(mapped_keypoints[kp_index][0]),
                        "y": int(mapped_keypoints[kp_index][1]),
                        "confidence": float(kp_scores[kp_index]),
                    }
                )

            pose = {
                "person_id": len(poses),
                "bbox": {
                    "x": int(xmin),
                    "y": int(ymin),
                    "width": int(xmax - xmin),
                    "height": int(ymax - ymin),
                },
                "bbox_confidence": float(scores[idx][0]),
                "keypoints": pose_keypoints,
            }

            if self.config.skeleton_connections:
                pose["skeleton"] = [
                    {
                        "from": COCO_KEYPOINTS[pair[0] - 1],
                        "to": COCO_KEYPOINTS[pair[1] - 1],
                        "from_index": pair[0] - 1,
                        "to_index": pair[1] - 1,
                    }
                    for pair in COCO_SKELETON
                    if kp_scores[pair[0] - 1] >= keypoint_threshold
                    and kp_scores[pair[1] - 1] >= keypoint_threshold
                ]

            poses.append(pose)

        response = {
            "poses": poses,
            "count": len(poses),
            "inference_time_ms": inference_time_ms,
            "image_size": {"width": orig_w, "height": orig_h},
        }

        return response

    async def shutdown(self):
        """Unload model and clean up resources."""
        if self.infer:
            logger.info("Unloading model")
            self.infer.close()
            self.infer = None
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
                
                def _as_float(value):
                    return float(value) if value is not None else None

                def _as_int(value):
                    return int(value) if value is not None else None

                params = {}
                if 'confidence_threshold' in payload:
                    params['confidence_threshold'] = _as_float(payload.get('confidence_threshold'))
                if 'iou_threshold' in payload:
                    params['iou_threshold'] = _as_float(payload.get('iou_threshold'))
                if 'keypoint_threshold' in payload:
                    params['keypoint_threshold'] = _as_float(payload.get('keypoint_threshold'))
                if 'max_detections' in payload:
                    params['max_detections'] = _as_int(payload.get('max_detections'))
            
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
    service = None
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
        if service is not None:
            await service.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
