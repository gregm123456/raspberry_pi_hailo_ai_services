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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from aiohttp import web
    import numpy as np
    from PIL import Image
    import yaml
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip3 install aiohttp pyyaml numpy pillow")
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
        self.output_format = "numpy"  # numpy, image, or both
        self.colormap = "viridis"  # viridis, plasma, magma, turbo, jet
        self.normalize = True
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
            
            logger.info(f"Loaded config from {CONFIG_JSON}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise


class DepthEstimator:
    """Depth estimation inference engine using Hailo-10H NPU."""
    
    def __init__(self, config: DepthServiceConfig):
        self.config = config
        self.model = None
        self.is_loaded = False
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
    
    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing depth model: {self.config.model_name}")
        
        try:
            # TODO: Implement HailoRT depth model loading
            # This is a placeholder for the actual Hailo depth estimation integration
            # In production, this would:
            # 1. Load the HEF via HailoRT SDK
            # 2. Initialize NPU device (/dev/hailo0)
            # 3. Allocate input/output tensors
            # 4. Verify device memory availability
            
            logger.info(f"Model initialization placeholder (HailoRT {self.config.model_name})")
            logger.info(f"Depth type: {self.config.model_type}")
            self.is_loaded = True
            
        except Exception as e:
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
            output_format: Output format (numpy, image, both)
        
        Returns:
            Dict containing depth map, metadata, and optionally visualization
        """
        
        if not self.is_loaded:
            raise RuntimeError("Model not loaded")
        
        # Use config defaults if not provided
        normalize = normalize if normalize is not None else self.config.normalize
        colormap = colormap or self.config.colormap
        output_format = output_format or self.config.output_format
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Load and prepare image
            img = Image.open(io.BytesIO(image_data))
            img_array = np.array(img)
            
            # TODO: Implement actual Hailo depth inference
            # This is a placeholder for HailoRT depth estimation
            # In production, this would:
            # 1. Preprocess image (resize, normalize, convert format)
            # 2. Copy to HailoRT input tensor
            # 3. Run inference on NPU
            # 4. Read output tensor (depth map)
            # 5. Postprocess (denormalize, colormap if requested)
            
            # Placeholder: Generate synthetic depth map
            height, width = img_array.shape[:2]
            depth_map = self._generate_placeholder_depth(height, width)
            
            if normalize:
                depth_map = self._normalize_depth(depth_map)
            
            inference_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Build response
            result = {
                "model": self.config.model_name,
                "model_type": self.config.model_type,
                "input_shape": list(img_array.shape),
                "depth_shape": list(depth_map.shape),
                "inference_time_ms": round(inference_time_ms, 2),
                "normalized": normalize
            }
            
            # Add depth data based on output format
            if output_format in ["numpy", "both"]:
                result["depth_map"] = self._encode_numpy(depth_map)
            
            if output_format in ["image", "both"]:
                result["depth_image"] = self._colorize_depth(depth_map, colormap)
            
            return result
            
        except Exception as e:
            logger.error(f"Depth estimation failed: {e}")
            raise
    
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
    
    def _encode_numpy(self, array: np.ndarray) -> str:
        """Encode NumPy array as base64 string."""
        # Save as compressed NPZ in memory
        buffer = io.BytesIO()
        np.savez_compressed(buffer, depth=array)
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
        if self.model:
            logger.info("Unloading depth model")
            # TODO: Properly unload HailoRT model
            self.model = None
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
                "stereo": False,  # TODO: Add stereo support
                "output_formats": ["numpy", "image", "both"],
                "colormaps": ["viridis", "plasma", "magma", "turbo", "jet"]
            }
        })
    
    async def estimate(self, request: web.Request) -> web.Response:
        """POST /v1/depth/estimate - Depth estimation inference."""
        
        try:
            # Parse multipart form or JSON
            if request.content_type.startswith('multipart/form-data'):
                reader = await request.multipart()
                
                image_data = None
                params = {}
                
                async for part in reader:
                    if part.name == 'image':
                        image_data = await part.read()
                    elif part.name in ['normalize', 'colormap', 'output_format']:
                        params[part.name] = await part.text()
                
                if not image_data:
                    return web.json_response(
                        {"error": {"message": "Missing 'image' field", "type": "invalid_request"}},
                        status=400
                    )
                
            elif request.content_type == 'application/json':
                payload = await request.json()
                
                # Expect base64-encoded image
                image_b64 = payload.get('image')
                if not image_b64:
                    return web.json_response(
                        {"error": {"message": "Missing 'image' field", "type": "invalid_request"}},
                        status=400
                    )
                
                image_data = base64.b64decode(image_b64)
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
    app = web.Application(client_max_size=50 * 1024 * 1024)  # 50MB max upload
    
    # Routes
    app.router.add_get('/health', handler.health)
    app.router.add_get('/health/ready', handler.health_ready)
    app.router.add_get('/v1/info', handler.info)
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
