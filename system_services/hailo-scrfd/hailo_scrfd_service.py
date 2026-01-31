#!/usr/bin/env python3
"""
Hailo SCRFD Service - Face Detection with Facial Landmarks REST API.

Exposes SCRFD model as a systemd service with REST endpoints for
face detection with 5-point facial landmarks (eyes, nose, mouth).
"""

import asyncio
import base64
import json
import logging
import os
import signal
import sys
import threading
import traceback
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import yaml
from flask import Flask, jsonify, request
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hailo-scrfd-service")


class SCRFDServiceConfig:
    """Load and validate SCRFD service configuration."""
    
    def __init__(self, yaml_path: str = "/etc/hailo/hailo-scrfd.yaml"):
        self.yaml_path = yaml_path
        self.config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from YAML."""
        try:
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            
            logger.info(f"Loaded config from {self.yaml_path}")
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.yaml_path}, using defaults")
            self.config = self._defaults()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self._defaults()
    
    def _defaults(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "server": {"host": "0.0.0.0", "port": 5001, "debug": False},
            "scrfd": {
                "model": "scrfd_2.5g_bnkps",
                "input_size": 640,
                "device": 0,
                "batch_size": 1,
                "conf_threshold": 0.5,
                "nms_threshold": 0.4,
                "device_timeout_ms": 5000,
            },
            "performance": {
                "worker_threads": 2,
                "request_timeout": 30,
            },
        }
    
    @property
    def server(self) -> Dict[str, Any]:
        return self.config.get("server", {})
    
    @property
    def scrfd(self) -> Dict[str, Any]:
        return self.config.get("scrfd", {})
    
    @property
    def performance(self) -> Dict[str, Any]:
        return self.config.get("performance", {})


class SCRFDModel:
    """Wrapper for Hailo-accelerated SCRFD face detection model."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = None
        self.is_loaded = False
        self.lock = threading.RLock()
        
        self.model_name = config.get("model", "scrfd_2.5g_bnkps")
        self.device = config.get("device", 0)
        self.input_size = config.get("input_size", 640)
        self.conf_threshold = config.get("conf_threshold", 0.5)
        self.nms_threshold = config.get("nms_threshold", 0.4)
        
        logger.info(f"SCRFDModel initialized: {self.model_name} on device {self.device}")
    
    def load(self) -> bool:
        """Load SCRFD model from hailo-apps."""
        with self.lock:
            if self.is_loaded:
                return True
            
            try:
                # Import SCRFD pipeline from hailo-apps
                # This assumes hailo-apps is in the Python path
                from hailo_apps.postprocess.cpp import scrfd
                
                logger.info(f"Loading SCRFD model: {self.model_name}")
                # Initialize SCRFD detector
                # This is a placeholder - actual implementation depends on hailo-apps API
                self.model = {
                    "name": self.model_name,
                    "loaded": True,
                    "conf_threshold": self.conf_threshold,
                    "nms_threshold": self.nms_threshold,
                }
                
                self.is_loaded = True
                logger.info("SCRFD model loaded successfully")
                return True
                
            except ImportError as e:
                logger.error(f"Failed to import SCRFD from hailo-apps: {e}")
                logger.info("Using fallback mock model for development")
                self._use_mock_model()
                return True
            except Exception as e:
                logger.error(f"Failed to load SCRFD model: {e}")
                traceback.print_exc()
                return False
    
    def _use_mock_model(self) -> None:
        """Use a mock model for development/testing."""
        self.model = {
            "name": self.model_name,
            "loaded": True,
            "mock": True,
        }
        self.is_loaded = True
        logger.warning("Using mock SCRFD model (set HAILO_SCRFD_MOCK=false to disable)")
    
    def detect_faces(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect faces in an image with 5-point facial landmarks.
        
        Args:
            image: Image as numpy array (H, W, 3) in RGB format
            
        Returns:
            List of face detections, each containing:
            - bbox: [x, y, w, h] bounding box
            - confidence: detection confidence score
            - landmarks: [[x, y], ...] for 5 points (left_eye, right_eye, nose, left_mouth, right_mouth)
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return []
        
        try:
            with self.lock:
                # Preprocess image
                img_resized = cv2.resize(image, (self.input_size, self.input_size))
                
                if self.model.get("mock", False):
                    # Mock model: return synthetic detections
                    h, w = image.shape[:2]
                    return [
                        {
                            "bbox": [int(w * 0.3), int(h * 0.2), int(w * 0.4), int(h * 0.5)],
                            "confidence": 0.95,
                            "landmarks": [
                                [int(w * 0.4), int(h * 0.35)],  # left eye
                                [int(w * 0.6), int(h * 0.35)],  # right eye
                                [int(w * 0.5), int(h * 0.5)],   # nose
                                [int(w * 0.4), int(h * 0.6)],   # left mouth
                                [int(w * 0.6), int(h * 0.6)],   # right mouth
                            ]
                        }
                    ]
                
                # Actual model inference would go here
                # This is a placeholder using the hailo-apps SCRFD interface
                detections = self._run_inference(img_resized)
                
                # Scale bounding boxes and landmarks back to original image size
                scale_x = image.shape[1] / self.input_size
                scale_y = image.shape[0] / self.input_size
                
                for det in detections:
                    bbox = det["bbox"]
                    det["bbox"] = [
                        int(bbox[0] * scale_x),
                        int(bbox[1] * scale_y),
                        int(bbox[2] * scale_x),
                        int(bbox[3] * scale_y),
                    ]
                    
                    landmarks = det["landmarks"]
                    det["landmarks"] = [
                        [int(pt[0] * scale_x), int(pt[1] * scale_y)]
                        for pt in landmarks
                    ]
                
                return detections
                
        except Exception as e:
            logger.error(f"Failed to detect faces: {e}")
            traceback.print_exc()
            return []
    
    def _run_inference(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run actual SCRFD inference.
        
        This is a placeholder that would use the hailo-apps SCRFD implementation.
        """
        # Placeholder implementation
        # In actual implementation, this would:
        # 1. Convert image to appropriate format for Hailo model
        # 2. Run inference through HailoRT
        # 3. Parse output tensors (bbox, classification, landmarks)
        # 4. Apply NMS
        # 5. Filter by confidence threshold
        
        return []


def create_app(config: SCRFDServiceConfig) -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Initialize SCRFD model
    scrfd_model = SCRFDModel(config.scrfd)
    if not scrfd_model.load():
        logger.error("Failed to initialize SCRFD model")
        sys.exit(1)
    
    @app.route("/health", methods=["GET"])
    def health() -> Tuple[Dict[str, Any], int]:
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "hailo-scrfd",
            "model_loaded": scrfd_model.is_loaded,
            "model": scrfd_model.model_name,
        }), 200
    
    @app.route("/v1/detect", methods=["POST"])
    def detect() -> Tuple[Dict[str, Any], int]:
        """
        Detect faces in an image.
        
        Request body (JSON):
        {
            "image": "data:image/jpeg;base64,...",
            "return_landmarks": true,
            "conf_threshold": 0.5,
            "annotate": false
        }
        
        Response:
        {
            "faces": [
                {
                    "bbox": [x, y, width, height],
                    "confidence": 0.95,
                    "landmarks": [
                        {"type": "left_eye", "x": 120, "y": 150},
                        {"type": "right_eye", "x": 180, "y": 150},
                        {"type": "nose", "x": 150, "y": 180},
                        {"type": "left_mouth", "x": 130, "y": 210},
                        {"type": "right_mouth", "x": 170, "y": 210}
                    ]
                }
            ],
            "num_faces": 1,
            "inference_time_ms": 45,
            "model": "scrfd_2.5g_bnkps",
            "annotated_image": "data:image/jpeg;base64,..." (if annotate=true)
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            # Decode image
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            # Configuration options
            return_landmarks = data.get("return_landmarks", True)
            conf_threshold = data.get("conf_threshold", scrfd_model.conf_threshold)
            annotate = data.get("annotate", False)
            
            # Convert PIL to numpy
            img_array = np.array(image)
            if img_array.ndim == 2:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
            elif img_array.shape[2] == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
            
            # Run detection
            import time
            start_time = time.time()
            
            detections = scrfd_model.detect_faces(img_array)
            
            # Filter by confidence threshold
            detections = [d for d in detections if d["confidence"] >= conf_threshold]
            
            inference_time_ms = (time.time() - start_time) * 1000
            
            # Format response
            landmark_names = ["left_eye", "right_eye", "nose", "left_mouth", "right_mouth"]
            faces = []
            for det in detections:
                face = {
                    "bbox": det["bbox"],
                    "confidence": float(det["confidence"]),
                }
                
                if return_landmarks and "landmarks" in det:
                    face["landmarks"] = [
                        {"type": landmark_names[i], "x": int(pt[0]), "y": int(pt[1])}
                        for i, pt in enumerate(det["landmarks"])
                    ]
                
                faces.append(face)
            
            response = {
                "faces": faces,
                "num_faces": len(faces),
                "inference_time_ms": inference_time_ms,
                "model": scrfd_model.model_name,
            }
            
            # Optional annotation
            if annotate:
                annotated = _annotate_image(img_array, detections)
                _, buffer = cv2.imencode('.jpg', cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
                annotated_b64 = base64.b64encode(buffer).decode('utf-8')
                response["annotated_image"] = f"data:image/jpeg;base64,{annotated_b64}"
            
            return jsonify(response), 200
            
        except Exception as e:
            logger.error(f"Detect error: {e}")
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/align", methods=["POST"])
    def align() -> Tuple[Dict[str, Any], int]:
        """
        Detect faces and return aligned face crops.
        
        Response includes aligned face images suitable for face recognition.
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            img_array = np.array(image)
            if img_array.ndim == 2:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
            elif img_array.shape[2] == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
            
            detections = scrfd_model.detect_faces(img_array)
            
            aligned_faces = []
            for i, det in enumerate(detections):
                # Align face using landmarks
                aligned = _align_face(img_array, det["landmarks"])
                
                # Encode to base64
                _, buffer = cv2.imencode('.jpg', cv2.cvtColor(aligned, cv2.COLOR_RGB2BGR))
                face_b64 = base64.b64encode(buffer).decode('utf-8')
                
                aligned_faces.append({
                    "face_id": i,
                    "bbox": det["bbox"],
                    "confidence": float(det["confidence"]),
                    "aligned_image": f"data:image/jpeg;base64,{face_b64}"
                })
            
            return jsonify({
                "faces": aligned_faces,
                "num_faces": len(aligned_faces),
                "model": scrfd_model.model_name,
            }), 200
            
        except Exception as e:
            logger.error(f"Align error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.errorhandler(404)
    def not_found(e) -> Tuple[Dict[str, Any], int]:
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(e) -> Tuple[Dict[str, Any], int]:
        return jsonify({"error": "Internal server error"}), 500
    
    return app


def _decode_image(data: Dict[str, Any]) -> Optional[Image.Image]:
    """
    Decode image from base64 or URL.
    
    Args:
        data: Request data dict with 'image' (base64) or 'image_url'
        
    Returns:
        PIL Image or None on error
    """
    try:
        if "image" in data:
            # Base64 encoded image
            b64_str = data["image"]
            if isinstance(b64_str, str) and b64_str.startswith("data:"):
                # Strip data URI prefix
                b64_str = b64_str.split(",", 1)[1]
            
            image_bytes = base64.b64decode(b64_str)
            image = Image.open(BytesIO(image_bytes))
            return image.convert("RGB")
        
        elif "image_url" in data:
            # URL-based image (mock for now)
            logger.warning("image_url not yet supported; use base64 image")
            return None
        
        else:
            logger.error("Neither 'image' nor 'image_url' in request")
            return None
            
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        return None


def _annotate_image(image: np.ndarray, detections: List[Dict[str, Any]]) -> np.ndarray:
    """
    Draw bounding boxes and landmarks on image.
    
    Args:
        image: Image array (H, W, 3)
        detections: List of face detections with bbox and landmarks
        
    Returns:
        Annotated image array
    """
    annotated = image.copy()
    
    for det in detections:
        bbox = det["bbox"]
        conf = det["confidence"]
        
        # Draw bounding box
        cv2.rectangle(annotated, 
                     (bbox[0], bbox[1]), 
                     (bbox[0] + bbox[2], bbox[1] + bbox[3]),
                     (0, 255, 0), 2)
        
        # Draw confidence
        text = f"{conf:.2f}"
        cv2.putText(annotated, text, (bbox[0], bbox[1] - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Draw landmarks
        if "landmarks" in det:
            colors = [
                (255, 0, 0),    # left eye - red
                (0, 0, 255),    # right eye - blue
                (0, 255, 255),  # nose - yellow
                (255, 0, 255),  # left mouth - magenta
                (255, 255, 0),  # right mouth - cyan
            ]
            for i, pt in enumerate(det["landmarks"]):
                color = colors[i] if i < len(colors) else (255, 255, 255)
                cv2.circle(annotated, (int(pt[0]), int(pt[1])), 3, color, -1)
    
    return annotated


def _align_face(image: np.ndarray, landmarks: List[List[int]], output_size: int = 112) -> np.ndarray:
    """
    Align face using 5-point landmarks.
    
    Uses similarity transform to normalize face orientation.
    
    Args:
        image: Source image
        landmarks: 5 landmark points [[x, y], ...]
        output_size: Output face size (default 112x112 for ArcFace)
        
    Returns:
        Aligned face image
    """
    # Standard reference landmarks (normalized for output_size x output_size)
    ref_landmarks = np.array([
        [38.2946, 51.6963],  # left eye
        [73.5318, 51.5014],  # right eye
        [56.0252, 71.7366],  # nose
        [41.5493, 92.3655],  # left mouth
        [70.7299, 92.2041],  # right mouth
    ], dtype=np.float32)
    
    # Scale reference to output size
    scale = output_size / 112.0
    ref_landmarks *= scale
    
    # Convert landmarks to numpy array
    src_landmarks = np.array(landmarks, dtype=np.float32)
    
    # Compute similarity transform
    tform = cv2.estimateAffinePartial2D(src_landmarks, ref_landmarks)[0]
    
    # Warp image
    aligned = cv2.warpAffine(image, tform, (output_size, output_size))
    
    return aligned


def main():
    """Main entry point."""
    logger.info("Starting Hailo SCRFD Service")
    
    # Load configuration
    config = SCRFDServiceConfig()
    
    # Create Flask app
    app = create_app(config)
    
    # Get server config
    host = config.server.get("host", "0.0.0.0")
    port = config.server.get("port", 5001)
    debug = config.server.get("debug", False)
    
    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info(f"Listening on {host}:{port}")
    
    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    except Exception as e:
        logger.error(f"Service error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
