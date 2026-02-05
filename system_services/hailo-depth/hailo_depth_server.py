#!/usr/bin/env python3
"""
Hailo Depth Service - Monocular/Stereo Depth Estimation on Hailo-10H

REST API server exposing depth estimation inference.
Supports image upload and returns depth maps as NumPy arrays or visualization.
"""

import asyncio
import base64
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from urllib.request import urlopen

try:
    from aiohttp import web
    import numpy as np
    from PIL import Image
    import yaml
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip3 install aiohttp pyyaml numpy pillow")
    sys.exit(1)

try:
    from hailo_apps.python.core.common.hailo_inference import HailoInfer
    from hailo_apps.python.core.common.hef_utils import get_hef_input_shape
except ImportError as e:
    print(f"Error: HailoRT/Hailo apps not available: {e}")
    print("Ensure hailo-apps is on PYTHONPATH and HailoRT is installed.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('hailo-depth')

# Configuration paths
XDG_CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', '/etc/xdg')
CONFIG_JSON = os.path.join(XDG_CONFIG_HOME, 'hailo-depth', 'hailo-depth.json')


class DepthServiceConfig:
    """Configuration management."""
    
    def __init__(self):
        self.server_host = "0.0.0.0"
        self.server_port = 11436
        self.model_name = "scdepthv3"
        self.model_type = "monocular"  # monocular or stereo
        self.keep_alive = -1
        self.output_format = "both"  # numpy, image, or both
        self.colormap = "viridis"  # viridis, plasma, magma, turbo, jet
        self.normalize = True
        self.include_stats = True
        self.depth_png_16 = False
        self.allow_local_paths = False
        self.allow_image_url = True
        self.max_image_mb = 50
        self.model_dir = "/var/lib/hailo-depth/resources/models"
        self.postprocess_dir = "/var/lib/hailo-depth/resources/postprocess"
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
            self.model_type = model.get('type', self.model_type)
            self.keep_alive = model.get('keep_alive', self.keep_alive)
            
            # Parse output config
            output = config.get('output', {})
            self.output_format = output.get('format', self.output_format)
            self.colormap = output.get('colormap', self.colormap)
            self.normalize = output.get('normalize', self.normalize)
            self.include_stats = output.get('include_stats', self.include_stats)
            self.depth_png_16 = output.get('depth_png_16', self.depth_png_16)
            
            # Parse input config
            input_cfg = config.get('input', {})
            self.allow_local_paths = input_cfg.get('allow_local_paths', self.allow_local_paths)
            self.allow_image_url = input_cfg.get('allow_image_url', self.allow_image_url)
            self.max_image_mb = input_cfg.get('max_image_mb', self.max_image_mb)
            
            # Parse resources config
            resources = config.get('resources', {})
            self.model_dir = resources.get('model_dir', self.model_dir)
            self.postprocess_dir = resources.get('postprocess_dir', self.postprocess_dir)
            
            logger.info(f"Loaded config from {CONFIG_JSON}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise


class DepthEstimator:
    """Depth estimation inference engine using Hailo-10H NPU."""
    
    def __init__(self, config: DepthServiceConfig):
        self.config = config
        self.model = None
        self.hailo_infer = None
        self.input_shape = None
        self.input_layout = None
        self.input_height = None
        self.input_width = None
        self.input_channels = None
        self.infer_lock = asyncio.Lock()
        self.is_loaded = False
        self.last_error = None
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
        self.inference_count = 0
    
    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing depth model: {self.config.model_name}")
        logger.info(f"Model directory: {self.config.model_dir}")
        logger.info(f"Postprocess directory: {self.config.postprocess_dir}")
        
        try:
            # Verify model and postprocess files exist
            model_hef = os.path.join(
                self.config.model_dir,
                f"{self.config.model_name}.hef"
            )
            
            if not os.path.exists(model_hef):
                raise FileNotFoundError(f"Model HEF not found at {model_hef}")

            # Resolve input shape from HEF
            try:
                self.input_shape = get_hef_input_shape(model_hef)
            except Exception as e:
                logger.warning(f"Failed to parse HEF shape; falling back: {e}")
                self.input_shape = None

            # Initialize Hailo inference wrapper
            start_time = time.time()
            self.hailo_infer = HailoInfer(
                model_hef,
                batch_size=1,
                input_type="UINT8",
                output_type="FLOAT32",
                priority=0
            )

            if self.input_shape is None:
                self.input_shape = self.hailo_infer.get_input_shape()

            self._parse_input_shape(self.input_shape)
            self.load_time_ms = int((time.time() - start_time) * 1000)

            logger.info(f"HailoRT initialized in {self.load_time_ms}ms")
            logger.info(f"Depth type: {self.config.model_type}")
            logger.info(
                "Input shape: %s, layout=%s, size=%sx%s",
                self.input_shape,
                self.input_layout,
                self.input_width,
                self.input_height,
            )
            logger.info(
                "Config: output_format=%s, normalize=%s, include_stats=%s",
                self.config.output_format,
                self.config.normalize,
                self.config.include_stats,
            )
            self.is_loaded = True
            self.last_error = None
            
        except Exception as e:
            self.last_error = str(e)
            if "HAILO_OUT_OF_PHYSICAL_DEVICES" in self.last_error:
                logger.warning("Hailo device busy; service will retry on demand")
                self.is_loaded = False
                return
            logger.error(f"Model initialization failed: {e}")
            raise
    
    async def estimate_depth(
        self,
        image_data: bytes,
        normalize: bool = None,
        colormap: str = None,
        output_format: str = None
    ) -> Dict[str, Any]:
        """
        Perform depth estimation on input image.
        
        Args:
            image_data: Raw image bytes (JPEG, PNG, etc.)
            normalize: Whether to normalize depth values (0-1 range)
            colormap: Colormap for visualization (viridis, plasma, etc.)
            output_format: Output format (numpy, image, both, depth_png_16)
        
        Returns:
            Dict containing depth map, metadata, and optionally visualization
        """
        
        if not self.is_loaded:
            await self.initialize()
        if not self.is_loaded:
            raise RuntimeError("Model not loaded")
        
        # Use config defaults if not provided
        normalize = normalize if normalize is not None else self.config.normalize
        colormap = colormap or self.config.colormap
        output_format = output_format or self.config.output_format
        
        start_time = time.time()
        
        try:
            # Load and prepare image
            img = Image.open(io.BytesIO(image_data))
            orig_width, orig_height = img.size
            
            # Preprocess image for model input
            input_tensor = self._preprocess_image(img)

            # Run HailoRT inference (threaded to avoid blocking event loop)
            async with self.infer_lock:
                output = await asyncio.to_thread(self._run_inference_sync, input_tensor)

            depth_map = self._extract_depth_output(output)
            depth_map = depth_map.astype(np.float32)

            # Resize back to original size if needed
            if depth_map.shape[:2] != (orig_height, orig_width):
                depth_map = self._resize_depth(depth_map, (orig_width, orig_height))
            
            if normalize:
                depth_map = self._normalize_depth(depth_map)
            
            inference_time_ms = (time.time() - start_time) * 1000
            self.inference_count += 1
            
            # Build response
            result = {
                "model": self.config.model_name,
                "model_type": self.config.model_type,
                "input_shape": [orig_height, orig_width, 3],
                "depth_shape": list(depth_map.shape),
                "inference_time_ms": round(inference_time_ms, 2),
                "normalized": normalize
            }
            
            # Add stats if requested
            if self.config.include_stats:
                result["stats"] = self._compute_depth_stats(depth_map)
            
            # Add depth data based on output format
            if output_format in ["numpy", "both"]:
                result["depth_map"] = self._encode_numpy(depth_map)
            
            if output_format in ["image", "both"]:
                result["depth_image"] = self._colorize_depth(depth_map, colormap)
            
            if output_format == "depth_png_16":
                result["depth_png_16"] = self._encode_depth_16bit(depth_map)
            
            return result
            
        except Exception as e:
            logger.error(f"Depth estimation failed: {e}", exc_info=True)
            raise

    def _parse_input_shape(self, shape: tuple) -> None:
        """Parse HEF input shape and infer layout."""
        if len(shape) == 4:
            batch, d1, d2, d3 = shape
            if d1 in (1, 3, 4) and d2 > 8 and d3 > 8:
                self.input_layout = "NCHW"
                self.input_channels = d1
                self.input_height = d2
                self.input_width = d3
            elif d3 in (1, 3, 4) and d1 > 8 and d2 > 8:
                self.input_layout = "NHWC"
                self.input_channels = d3
                self.input_height = d1
                self.input_width = d2
            else:
                self.input_layout = "NHWC"
                self.input_channels = d3
                self.input_height = d1
                self.input_width = d2
        elif len(shape) == 3:
            d1, d2, d3 = shape
            if d3 in (1, 3, 4):
                self.input_layout = "HWC"
                self.input_height = d1
                self.input_width = d2
                self.input_channels = d3
            else:
                self.input_layout = "CHW"
                self.input_channels = d1
                self.input_height = d2
                self.input_width = d3
        else:
            raise ValueError(f"Unsupported input shape: {shape}")

    def _preprocess_image(self, img: Image.Image) -> np.ndarray:
        """Resize and format image for model input."""
        if self.input_width is None or self.input_height is None:
            raise RuntimeError("Input shape not initialized")

        # Convert to expected channels
        if self.input_channels == 1:
            if img.mode != "L":
                img = img.convert("L")
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")

        img_resized = img.resize((self.input_width, self.input_height), Image.BILINEAR)
        img_array = np.array(img_resized, dtype=np.uint8)

        if self.input_channels == 1:
            if img_array.ndim == 2:
                img_array = np.expand_dims(img_array, axis=-1)

        # Apply layout
        if self.input_layout in ("NCHW", "CHW"):
            img_array = np.transpose(img_array, (2, 0, 1))

        # Add batch dimension if needed
        if self.input_layout in ("NCHW", "NHWC"):
            img_array = np.expand_dims(img_array, axis=0)

        return img_array

    def _run_inference_sync(self, input_tensor: np.ndarray) -> Any:
        """Run a single inference and return output."""
        if self.hailo_infer is None:
            raise RuntimeError("Hailo inference not initialized")

        result = {"output": None, "error": None}
        done = threading.Event()

        def _callback(completion_info, bindings_list, **kwargs):
            if completion_info and getattr(completion_info, "exception", None):
                result["error"] = completion_info.exception
                done.set()
                return

            outputs = []
            for bindings in bindings_list:
                if len(bindings._output_names) == 1:
                    outputs.append(bindings.output().get_buffer())
                else:
                    outputs.append({
                        name: bindings.output(name).get_buffer()
                        for name in bindings._output_names
                    })
            result["output"] = outputs[0] if outputs else None
            done.set()

        self.hailo_infer.run([input_tensor], _callback)
        if self.hailo_infer.last_infer_job is not None:
            self.hailo_infer.last_infer_job.wait(10000)
        if not done.wait(10):
            raise TimeoutError("Inference did not complete in time")
        if result["error"] is not None:
            raise RuntimeError(f"Inference error: {result['error']}")
        if result["output"] is None:
            raise RuntimeError("Inference returned no output")
        return result["output"]

    def _extract_depth_output(self, output: Any) -> np.ndarray:
        """Extract a 2D depth map from model output."""
        if isinstance(output, dict):
            # Choose the first output deterministically
            first_key = sorted(output.keys())[0]
            output = output[first_key]

        depth = np.squeeze(output)
        if depth.ndim != 2:
            # Try to flatten to 2D if possible
            if depth.ndim == 3:
                depth = depth[0] if depth.shape[0] in (1, 3) else depth[:, :, 0]
            else:
                raise ValueError(f"Unexpected depth output shape: {depth.shape}")

        return depth

    def _resize_depth(self, depth_map: np.ndarray, size: tuple) -> np.ndarray:
        """Resize depth map to original image size."""
        width, height = size
        depth_img = Image.fromarray(depth_map.astype(np.float32))
        depth_img = depth_img.resize((width, height), Image.BILINEAR)
        return np.array(depth_img, dtype=np.float32)
    
    def _generate_placeholder_depth(self, height: int, width: int) -> np.ndarray:
        """Generate synthetic depth map for testing (TODO: remove in production)."""
        # Create a radial gradient as placeholder
        y, x = np.ogrid[:height, :width]
        center_y, center_x = height / 2, width / 2
        depth = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        return depth.astype(np.float32)
    
    def _normalize_depth(self, depth_map: np.ndarray) -> np.ndarray:
        """Normalize depth values to 0-1 range."""
        min_val = depth_map.min()
        max_val = depth_map.max()
        if max_val - min_val > 0:
            return (depth_map - min_val) / (max_val - min_val)
        return depth_map
    
    def _compute_depth_stats(self, depth_map: np.ndarray) -> Dict[str, float]:
        """Compute depth statistics (with outlier rejection)."""
        flat_depth = depth_map.flatten()
        # Remove top 5% outliers
        threshold = np.percentile(flat_depth, 95)
        filtered = flat_depth[flat_depth <= threshold]
        
        return {
            "min": float(filtered.min()),
            "max": float(filtered.max()),
            "mean": float(filtered.mean()),
            "p95": float(threshold)
        }
    
    def _encode_numpy(self, array: np.ndarray) -> str:
        """Encode NumPy array as base64 string."""
        # Save as compressed NPZ in memory
        buffer = io.BytesIO()
        np.savez_compressed(buffer, depth=array)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')
    
    def _encode_depth_16bit(self, depth_map: np.ndarray) -> str:
        """Convert depth map to 16-bit grayscale PNG and return as base64."""
        # Normalize if not already
        normalized = self._normalize_depth(depth_map)
        
        # Convert to 16-bit (0-65535 range)
        depth_16bit = (normalized * 65535).astype(np.uint16)
        
        # Convert to PIL Image (grayscale 16-bit)
        img = Image.fromarray(depth_16bit, mode='I;16')
        
        # Encode as PNG
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')
    
    def _colorize_depth(self, depth_map: np.ndarray, colormap: str) -> str:
        """Convert depth map to colorized image and return as base64 PNG."""
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            
            # Normalize if not already
            normalized = self._normalize_depth(depth_map)
            
            # Apply colormap
            cmap = plt.get_cmap(colormap)
            colored = cmap(normalized)
            
            # Convert to 8-bit RGB
            img_array = (colored[:, :, :3] * 255).astype(np.uint8)
            img = Image.fromarray(img_array)
            
            # Encode as PNG
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode('utf-8')
            
        except ImportError:
            logger.warning("matplotlib not available, skipping colorization")
            return ""
    
    async def shutdown(self):
        """Unload model and clean up resources."""
        if self.hailo_infer:
            logger.info("Unloading depth model")
            try:
                self.hailo_infer.close()
            except Exception as e:
                logger.warning(f"Error during model unload: {e}")
            self.hailo_infer = None
        self.is_loaded = False


class APIHandler:
    """HTTP API request handlers."""
    
    def __init__(self, estimator: DepthEstimator):
        self.estimator = estimator
    
    async def health(self, request: web.Request) -> web.Response:
        """GET /health - Service status."""
        return web.json_response({
            "status": "ok",
            "service": "hailo-depth",
            "model": self.estimator.config.model_name,
            "model_type": self.estimator.config.model_type,
            "model_loaded": self.estimator.is_loaded,
            "last_error": self.estimator.last_error,
            "inference_count": self.estimator.inference_count,
            "uptime_seconds": (datetime.utcnow() - self.estimator.startup_time).total_seconds()
        })
    
    async def health_ready(self, request: web.Request) -> web.Response:
        """GET /health/ready - Readiness probe."""
        if self.estimator.is_loaded:
            return web.json_response({"ready": True})
        else:
            return web.json_response(
                {"ready": False, "reason": "model_loading"},
                status=503
            )
    
    async def info(self, request: web.Request) -> web.Response:
        """GET /v1/info - Service information."""
        return web.json_response({
            "service": "hailo-depth",
            "version": "1.0.0",
            "model": {
                "name": self.estimator.config.model_name,
                "type": self.estimator.config.model_type,
                "loaded": self.estimator.is_loaded
            },
            "capabilities": {
                "monocular": True,
                "stereo": self.estimator.config.model_type == "stereo",
                "output_formats": ["numpy", "image", "both", "depth_png_16"],
                "colormaps": ["viridis", "plasma", "magma", "turbo", "jet"]
            }
        })
    
    async def list_models(self, request: web.Request) -> web.Response:
        """GET /v1/models - List available models."""
        return web.json_response({
            "models": [
                {
                    "name": "scdepthv3",
                    "type": "monocular",
                    "description": "Efficient monocular depth estimation"
                }
                # TODO: Add stereo and other models
            ]
        })
    
    async def estimate(self, request: web.Request) -> web.Response:
        """POST /v1/depth/estimate - Depth estimation inference."""
        
        try:
            image_data = None
            params = {}
            
            # Parse multipart form or JSON
            if request.content_type and request.content_type.startswith('multipart/form-data'):
                reader = await request.multipart()
                
                async for part in reader:
                    if part.name == 'image':
                        image_data = await part.read()
                    elif part.name == 'image_right':
                        params['image_right'] = await part.read()
                    elif part.name in ['normalize', 'colormap', 'output_format']:
                        params[part.name] = await part.text()
                
                if not image_data:
                    return web.json_response(
                        {"error": {"message": "Missing 'image' field", "type": "invalid_request"}},
                        status=400
                    )
                
            elif request.content_type == 'application/json':
                payload = await request.json()
                
                # Expect base64-encoded image or URL
                if 'image' in payload:
                    image_b64 = payload.get('image')
                    if image_b64.startswith('data:'):
                        # Data URI format
                        image_data = base64.b64decode(image_b64.split(',', 1)[1])
                    else:
                        # Plain base64
                        image_data = base64.b64decode(image_b64)
                elif 'image_url' in payload and self.estimator.config.allow_image_url:
                    try:
                        image_url = payload['image_url']
                        with urlopen(image_url) as response:
                            image_data = response.read()
                    except Exception as e:
                        return web.json_response(
                            {"error": {"message": f"Failed to fetch image URL: {e}", "type": "invalid_request"}},
                            status=400
                        )
                else:
                    return web.json_response(
                        {"error": {"message": "Missing 'image' or 'image_url' field", "type": "invalid_request"}},
                        status=400
                    )
                
                params = {
                    'normalize': payload.get('normalize'),
                    'colormap': payload.get('colormap'),
                    'output_format': payload.get('output_format')
                }
            else:
                return web.json_response(
                    {"error": {"message": "Unsupported content type", "type": "invalid_request"}},
                    status=400
                )
            
            # Validate image size
            if len(image_data) > self.estimator.config.max_image_mb * 1024 * 1024:
                return web.json_response(
                    {"error": {"message": f"Image exceeds {self.estimator.config.max_image_mb}MB limit", "type": "invalid_request"}},
                    status=400
                )
            
            # Convert string booleans
            if isinstance(params.get('normalize'), str):
                params['normalize'] = params['normalize'].lower() == 'true'
            
            # Run depth estimation
            result = await self.estimator.estimate_depth(
                image_data=image_data,
                normalize=params.get('normalize'),
                colormap=params.get('colormap'),
                output_format=params.get('output_format')
            )
            
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Estimation error: {e}", exc_info=True)
            return web.json_response(
                {"error": {"message": str(e), "type": "internal_error"}},
                status=500
            )


async def create_app(estimator: DepthEstimator) -> web.Application:
    """Create aiohttp application."""
    handler = APIHandler(estimator)
    max_size = estimator.config.max_image_mb * 1024 * 1024
    app = web.Application(client_max_size=max_size)
    
    # Routes
    app.router.add_get('/health', handler.health)
    app.router.add_get('/health/ready', handler.health_ready)
    app.router.add_get('/v1/info', handler.info)
    app.router.add_get('/v1/models', handler.list_models)
    app.router.add_post('/v1/depth/estimate', handler.estimate)
    
    return app


async def main():
    """Main entry point."""
    try:
        # Load configuration
        config = DepthServiceConfig()
        logger.info(f"Hailo Depth Service starting")
        logger.info(f"Server: {config.server_host}:{config.server_port}")
        logger.info(f"Model: {config.model_name} ({config.model_type})")
        
        # Initialize estimator
        estimator = DepthEstimator(config)
        await estimator.initialize()
        
        # Create and start server
        app = await create_app(estimator)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.server_host, config.server_port)
        await site.start()
        
        logger.info(f"Service ready at http://{config.server_host}:{config.server_port}")
        logger.info(f"Health: GET /health")
        logger.info(f"API docs: POST /v1/depth/estimate")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
    
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await estimator.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
