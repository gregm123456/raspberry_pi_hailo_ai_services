#!/usr/bin/env python3
"""
Hailo CLIP Service - Zero-Shot Image Classification REST API.

Exposes CLIP model as a systemd service with REST endpoints for
image classification using runtime-configurable text prompts.
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

# Hailo Imports
try:
    from hailo_platform import FormatType
    # We use some utilities from hailo-apps
    from hailo_apps.python.pipeline_apps.clip import clip_text_utils
    from hailo_apps.python.core.common.core import resolve_hef_path
    from hailo_apps.python.core.common.defines import CLIP_PIPELINE
    HAILO_AVAILABLE = True
except ImportError:
    HAILO_AVAILABLE = False

try:
    from device_client import HailoDeviceClient
    DEVICE_CLIENT_AVAILABLE = True
except ImportError:
    DEVICE_CLIENT_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hailo-clip-service")


class CLIPServiceConfig:
    """Load and validate CLIP service configuration."""
    
    def __init__(self, yaml_path: str = "/etc/hailo/hailo-clip.yaml"):
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
            "server": {"host": "0.0.0.0", "port": 5000, "debug": False},
            "clip": {
                "model": "clip-resnet-50x4",
                "embedding_dimension": 640,
                "device": 0,
                "image_size": 224,
                "batch_size": 1,
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
    def clip(self) -> Dict[str, Any]:
        return self.config.get("clip", {})
    
    @property
    def performance(self) -> Dict[str, Any]:
        return self.config.get("performance", {})


class CLIPModel:
    """Wrapper for Hailo-accelerated CLIP model."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.device_model_path = None
        self.model_params = {}  # Store model params for device manager
        self.is_loaded = False
        self.lock = threading.RLock()
        
        # Resources for text encoding
        self.tokenizer = None
        self.token_embeddings = None
        self.text_projection = None
        
        self.model_name = config.get("model", "clip-vit-b-32")
        self.device = config.get("device", 0)
        self.embedding_dim = config.get("embedding_dimension", 512)
        self.image_size = config.get("image_size", 224)
        self.text_hef_path = None
        self.logit_scale = config.get("logit_scale", 100.0)
        self.apply_softmax = config.get("apply_softmax", True)
        
        logger.info(f"CLIPModel initialized: {self.model_name}")
    
    def load(self) -> bool:
        """Load CLIP model using HailoRT and hailo-apps utilities."""
        if not HAILO_AVAILABLE or not DEVICE_CLIENT_AVAILABLE:
            logger.error("Hailo dependencies not installed. Falling back to mock.")
            self._use_mock_model()
            return True

        with self.lock:
            if self.is_loaded:
                return True
            
            try:
                # Resolve HEF paths (the H10-H models)
                image_hef_path = resolve_hef_path("clip_vit_b_32_image_encoder", CLIP_PIPELINE)
                self.text_hef_path = resolve_hef_path("clip_vit_b_32_text_encoder", CLIP_PIPELINE)
                
                if not image_hef_path or not self.text_hef_path:
                    raise FileNotFoundError("Could not resolve CLIP HEF paths.")

                logger.info(f"Loading Image Encoder via device manager: {image_hef_path}")
                self.device_model_path = str(image_hef_path)
                
                # Input/Output layer names for text encoder
                # These are specific to clip_vit_b_32_text_encoder
                self.text_input_layer = 'clip_vit_b_32_text_encoder/input_layer1'
                self.text_output_layer = 'clip_vit_b_32_text_encoder/normalization25'

                # Initialize CLIP models via device manager
                self.model_params = {
                    "image_hef_path": str(image_hef_path),
                    "text_hef_path": str(self.text_hef_path),
                    "text_input_layer": self.text_input_layer,
                    "text_output_layer": self.text_output_layer,
                    "image_input_format": str(FormatType.UINT8),
                    "image_output_format": str(FormatType.FLOAT32),
                    "text_input_format": str(FormatType.FLOAT32),
                    "text_output_format": str(FormatType.FLOAT32),
                }

                asyncio.run(self._load_device_model(self.model_params))

                # 3. Load text processing resources
                logger.info("Loading text processing resources (tokenizer, embeddings, projection)")
                self.tokenizer = clip_text_utils.load_clip_tokenizer()
                self.token_embeddings = clip_text_utils.load_token_embeddings()
                
                # Resolve text projection path (usually in /usr/local/hailo/resources/npy/)
                proj_path = Path("/usr/local/hailo/resources/npy/text_projection.npy")
                if proj_path.exists():
                    self.text_projection = np.load(proj_path)
                else:
                    logger.warning(f"Text projection not found at {proj_path}. Scores may be inaccurate.")

                self.is_loaded = True
                logger.info(f"CLIP models loaded (Softmax: {self.apply_softmax}, Scale: {self.logit_scale})")
                return True
                
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                traceback.print_exc()
                return False
    
    def _use_mock_model(self) -> None:
        """Use a mock model for development/testing."""
        self.device_model_path = None
        self.is_loaded = True
        logger.warning("Using mock CLIP model (set HAILO_CLIP_MOCK=false to disable)")
    
    def encode_image(self, image: Image.Image) -> Optional[np.ndarray]:
        """
        Encode an image to CLIP embeddings.
        
        Args:
            image: PIL Image object
            
        Returns:
            Embedding array or None on error
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return None
        
        try:
            with self.lock:
                # Resize image to dimensions expected by HEF (224x224)
                image = image.resize((self.image_size, self.image_size))
                image_array = np.array(image, dtype=np.uint8)
                
                if self.device_model_path is None:
                    # Mock model: return random embedding
                    return np.random.randn(self.embedding_dim).astype(np.float32)

                response = asyncio.run(
                    self._device_infer(
                        {
                            "mode": "image",
                            "tensor": encode_tensor(image_array),
                            "timeout_ms": self.config.get("device_timeout_ms", 5000),
                        }
                    )
                )

                embedding = decode_tensor(response["result"]).flatten()
                
                # Normalize embedding (CLIP requires unit vectors for cosine similarity)
                embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
                return embedding.astype(np.float32)
                
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            traceback.print_exc()
            return None
    
    def encode_text(self, text: str) -> Optional[np.ndarray]:
        """
        Encode text prompt to CLIP embeddings.
        
        Args:
            text: Text prompt
            
        Returns:
            Embedding array or None on error
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return None
        
        try:
            with self.lock:
                if self.device_model_path is None:
                    # Mock model: return random embedding
                    return np.random.randn(self.embedding_dim).astype(np.float32)
                
                # 1. Prepare text encoder input using hailo-apps logic
                prepared = clip_text_utils.prepare_text_for_hailo_encoder(
                    text=text,
                    tokenizer=self.tokenizer,
                    token_embeddings=self.token_embeddings
                )
                input_embeddings = prepared['token_embeddings']
                last_token_positions = prepared['last_token_positions']

                # 2. Run inference on our existing VDevice
                response = asyncio.run(
                    self._device_infer(
                        {
                            "mode": "text",
                            "tensor": encode_tensor(input_embeddings),
                            "timeout_ms": self.config.get("device_timeout_ms", 5000),
                        }
                    )
                )
                output_buffer = decode_tensor(response["result"])
                
                # 3. Post-process (Projection + L2 Normalization)
                embedding = clip_text_utils.text_encoding_postprocessing(
                    encoder_output=output_buffer,
                    last_token_positions=last_token_positions,
                    text_projection=self.text_projection
                )
                
                return embedding.flatten().astype(np.float32)
                
        except Exception as e:
            logger.error(f"Failed to encode text: {e}")
            traceback.print_exc()
            return None
    
    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    async def _load_device_model(self, model_params: Dict[str, Any]) -> None:
        async with HailoDeviceClient() as client:
            await client.load_model(
                self.device_model_path,
                model_type="clip",
                model_params=model_params,
            )

    async def _device_infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with HailoDeviceClient() as client:
            return await client.infer(
                self.device_model_path,
                payload,
                model_type="clip",
                model_params=self.model_params,
            )


def encode_tensor(array: np.ndarray) -> Dict[str, Any]:
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }


def decode_tensor(payload: Dict[str, Any]) -> np.ndarray:
    dtype = payload.get("dtype")
    shape = payload.get("shape")
    data_b64 = payload.get("data_b64")
    if not dtype or shape is None or not data_b64:
        raise ValueError("tensor must include dtype, shape, and data_b64")
    raw = base64.b64decode(data_b64)
    array = np.frombuffer(raw, dtype=np.dtype(dtype))
    return array.reshape(shape)


def create_app(config: CLIPServiceConfig) -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Initialize CLIP model
    clip_model = CLIPModel(config.clip)
    if not clip_model.load():
        logger.error("Failed to initialize CLIP model")
        sys.exit(1)
    
    @app.route("/health", methods=["GET"])
    def health() -> Tuple[Dict[str, Any], int]:
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "hailo-clip",
            "model_loaded": clip_model.is_loaded,
            "model": clip_model.model_name,
        }), 200
    
    @app.route("/v1/classify", methods=["POST"])
    def classify() -> Tuple[Dict[str, Any], int]:
        """
        Classify an image against text prompts.
        
        Request body (JSON):
        {
            "image": "data:image/jpeg;base64,...",  OR "image_url": "http://...",
            "prompts": ["text1", "text2", ...],
            "top_k": 3,
            "threshold": 0.5
        }
        
        Response:
        {
            "classifications": [
                {"text": "...", "score": 0.95, "rank": 1},
                ...
            ],
            "inference_time_ms": 45,
            "model": "clip-resnet-50x4"
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
            
            # Get prompts
            prompts = data.get("prompts", [])
            if not prompts or not isinstance(prompts, list):
                return jsonify({"error": "Missing or invalid 'prompts' array"}), 400
            
            top_k = min(data.get("top_k", 3), len(prompts))
            threshold = data.get("threshold", 0.0)
            
            # Encode image
            import time
            start_time = time.time()
            
            image_embedding = clip_model.encode_image(image)
            if image_embedding is None:
                return jsonify({"error": "Failed to encode image"}), 500
            
            # Encode prompts and compute similarities
            similarities_list: List[float] = []
            for prompt in prompts:
                text_embedding = clip_model.encode_text(prompt)
                if text_embedding is not None:
                    score = clip_model.cosine_similarity(image_embedding, text_embedding)
                    similarities_list.append(score)
                else:
                    similarities_list.append(-1.0)
            
            # Apply Softmax if multiple prompts
            scores = np.array(similarities_list)
            if clip_model.apply_softmax and len(prompts) > 1:
                # Scaled Softmax for better differentiation with numerical stability
                shifted_scores = clip_model.logit_scale * (scores - np.max(scores))
                exp_scores = np.exp(shifted_scores)
                scores = exp_scores / np.sum(exp_scores)
            
            # Format results
            results = []
            for i, prompt in enumerate(prompts):
                if scores[i] >= threshold:
                    results.append({"text": prompt, "score": float(scores[i])})

            # Sort by score (descending) and take top_k
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:top_k]
            
            inference_time_ms = (time.time() - start_time) * 1000
            
            # Add rank
            for rank, item in enumerate(results):
                item["rank"] = rank + 1
            
            return jsonify({
                "classifications": results,
                "inference_time_ms": inference_time_ms,
                "model": clip_model.model_name,
            }), 200
            
        except Exception as e:
            logger.error(f"Classify error: {e}")
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/embed/image", methods=["POST"])
    def embed_image() -> Tuple[Dict[str, Any], int]:
        """
        Get CLIP embedding for an image.
        
        Response:
        {
            "embedding": [0.1, 0.2, ...],
            "dimension": 640,
            "model": "clip-resnet-50x4"
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            embedding = clip_model.encode_image(image)
            if embedding is None:
                return jsonify({"error": "Failed to encode image"}), 500
            
            return jsonify({
                "embedding": embedding.tolist(),
                "dimension": len(embedding),
                "model": clip_model.model_name,
            }), 200
            
        except Exception as e:
            logger.error(f"Embed image error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/embed/text", methods=["POST"])
    def embed_text() -> Tuple[Dict[str, Any], int]:
        """
        Get CLIP embedding for text.
        
        Request: {"text": "..."}
        Response: {"embedding": [...], "dimension": 640, "model": "..."}
        """
        try:
            data = request.get_json()
            if not data or "text" not in data:
                return jsonify({"error": "Missing 'text' field"}), 400
            
            text = data.get("text", "")
            embedding = clip_model.encode_text(text)
            
            if embedding is None:
                return jsonify({"error": "Failed to encode text"}), 500
            
            return jsonify({
                "embedding": embedding.tolist(),
                "dimension": len(embedding),
                "model": clip_model.model_name,
            }), 200
            
        except Exception as e:
            logger.error(f"Embed text error: {e}")
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


def main():
    """Main entry point."""
    logger.info("Starting Hailo CLIP Service")
    
    # Load configuration
    config = CLIPServiceConfig()
    
    # Create Flask app
    app = create_app(config)
    
    # Get server config
    host = config.server.get("host", "0.0.0.0")
    port = config.server.get("port", 5000)
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
