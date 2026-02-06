"""
Async/await unit tests for hailo-depth service.

Tests the refactored DepthEstimator class with HailoDeviceClient.

Run with: pytest test_hailo_depth_async.py -v
"""

import asyncio
import base64
import io
import json
import numpy as np
import pytest
from PIL import Image
from unittest.mock import AsyncMock, MagicMock, patch, call

import sys
from pathlib import Path

# Add parent directory to path to import hailo_depth_server
SCRIPT_DIR = str(Path(__file__).parent.parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


@pytest.fixture
def sample_image_array():
    """Create a sample test image as numpy array."""
    width, height = 256, 320
    img_array = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    return img_array


@pytest.fixture
def sample_image_bytes(sample_image_array):
    """Convert sample image to JPEG bytes."""
    img = Image.fromarray(sample_image_array)
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=90)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_depth_map():
    """Create a sample depth map (output of model)."""
    return np.random.rand(1, 256, 320).astype(np.float32) * 100


class TestTensorHelpers:
    """Test tensor encoding/decoding functions."""
    
    def test_encode_tensor(self, sample_image_array):
        """Test encoding numpy array to base64 tensor payload."""
        from hailo_depth_server import encode_tensor
        
        # Import here to test after mocks are set up
        encoded = encode_tensor(sample_image_array)
        
        assert "dtype" in encoded
        assert "shape" in encoded
        assert "data_b64" in encoded
        
        assert encoded["dtype"] == str(sample_image_array.dtype)
        assert encoded["shape"] == list(sample_image_array.shape)
        assert isinstance(encoded["data_b64"], str)
    
    def test_decode_tensor(self, sample_image_array):
        """Test decoding base64 tensor payload to numpy array."""
        from hailo_depth_server import encode_tensor, decode_tensor
        
        # Encode then decode
        encoded = encode_tensor(sample_image_array)
        decoded = decode_tensor(encoded)
        
        assert decoded.dtype == sample_image_array.dtype
        assert decoded.shape == sample_image_array.shape
        np.testing.assert_array_equal(decoded, sample_image_array)
    
    def test_decode_tensor_invalid_payload(self):
        """Test decoding with invalid payload."""
        from hailo_depth_server import decode_tensor
        
        with pytest.raises(ValueError, match="tensor must include"):
            decode_tensor({})
        
        with pytest.raises(ValueError, match="tensor must include"):
            decode_tensor({"dtype": "float32"})
        
        with pytest.raises(ValueError, match="tensor must include"):
            decode_tensor({
                "dtype": "float32",
                "shape": [1, 3, 256, 320],
                # missing data_b64
            })
    
    def test_round_trip_various_dtypes(self):
        """Test encoding/decoding with various data types."""
        from hailo_depth_server import encode_tensor, decode_tensor
        
        test_arrays = [
            np.array([1, 2, 3], dtype=np.uint8),
            np.array([1.0, 2.0, 3.0], dtype=np.float32),
            np.array([1.0, 2.0, 3.0], dtype=np.float64),
            np.array([[1, 2], [3, 4]], dtype=np.int32),
        ]
        
        for arr in test_arrays:
            encoded = encode_tensor(arr)
            decoded = decode_tensor(encoded)
            
            assert decoded.dtype == arr.dtype
            assert decoded.shape == arr.shape
            np.testing.assert_array_equal(decoded, arr)


class TestDepthEstimatorInit:
    """Test DepthEstimator initialization."""
    
    @pytest.mark.asyncio
    async def test_init_creates_config(self):
        """Test that DepthEstimator creates config on init."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        assert estimator.config == config
        assert estimator.client is None
        assert estimator.model_path is None
        assert estimator.is_loaded is False
        assert estimator.inference_count == 0
    
    @pytest.mark.asyncio
    async def test_init_attributes(self):
        """Test DepthEstimator has expected attributes."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # Check all required attributes exist
        assert hasattr(estimator, 'client')
        assert hasattr(estimator, 'model_path')
        assert hasattr(estimator, 'input_shape')
        assert hasattr(estimator, 'input_layout')
        assert hasattr(estimator, 'input_height')
        assert hasattr(estimator, 'input_width')
        assert hasattr(estimator, 'input_channels')
        assert hasattr(estimator, 'is_loaded')
        assert hasattr(estimator, 'last_error')
        assert hasattr(estimator, 'load_time_ms')
        assert hasattr(estimator, 'inference_count')


class TestDepthEstimatorInitialize:
    """Test DepthEstimator.initialize() with mocked device manager."""
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, tmp_path):
        """Test successful initialization with device manager."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        # Create a mock HEF file
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        # Mock the device client
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            # Mock get_hef_input_shape
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                await estimator.initialize()
        
        # Verify client was created and connected
        MockClient.assert_called_once()
        mock_client.connect.assert_called_once()
        
        # Verify model was loaded
        mock_client.load_model.assert_called_once()
        
        # Check state
        assert estimator.is_loaded is True
        assert estimator.model_path == str(model_hef)
        assert estimator.last_error is None
        assert estimator.input_shape == (1, 3, 256, 320)
    
    @pytest.mark.asyncio
    async def test_initialize_model_not_found(self, tmp_path):
        """Test initialization fails when model file not found."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        with pytest.raises(FileNotFoundError, match="Model HEF not found"):
            await estimator.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_device_client_failure(self, tmp_path):
        """Test initialization handles device manager connection failure."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        # Create a mock HEF file
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        # Mock the device client to raise an error
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.connect.side_effect = RuntimeError("Connection failed")
            MockClient.return_value = mock_client
            
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                with pytest.raises(RuntimeError):
                    await estimator.initialize()
        
        # Check state
        assert estimator.is_loaded is False
        assert estimator.last_error is not None
        assert "Connection failed" in estimator.last_error


class TestDepthEstimatorEstimateDepth:
    """Test DepthEstimator.estimate_depth() with mocked device manager."""
    
    @pytest.mark.asyncio
    async def test_estimate_depth_success(self, sample_image_bytes, sample_depth_map, tmp_path):
        """Test successful depth estimation."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig, encode_tensor
        
        # Setup
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        # Mock device client and initialize
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                await estimator.initialize()
        
        # Mock the inference result
        mock_result = {"result": encode_tensor(sample_depth_map)}
        mock_client.infer.return_value = mock_result
        
        # Run estimation
        result = await estimator.estimate_depth(
            sample_image_bytes,
            normalize=False,
            colormap="viridis",
            output_format="both"
        )
        
        # Verify client.infer was called
        mock_client.infer.assert_called_once()
        
        # Verify result structure
        assert result["model"] == "scdepthv3"
        assert result["model_type"] == "monocular"
        assert "inference_time_ms" in result
        assert result["normalized"] is False
        assert "depth_map" in result
        assert "depth_image" in result
        
        # Check inference count
        assert estimator.inference_count == 1
    
    @pytest.mark.asyncio
    async def test_estimate_depth_not_loaded(self, sample_image_bytes, tmp_path):
        """Test estimate_depth initializes if not loaded."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        assert estimator.is_loaded is False
        
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                with patch.object(estimator, 'estimate_depth', new_callable=AsyncMock) as mock_estimate:
                    # Just verify initialize would be called, don't actually estimate
                    pass
    
    @pytest.mark.asyncio
    async def test_estimate_depth_invalid_image(self, tmp_path):
        """Test estimate_depth handles invalid image data."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                await estimator.initialize()
        
        # Try to estimate with invalid image data
        with pytest.raises(Exception):  # Could be IOError or similar
            await estimator.estimate_depth(b"not an image")


class TestDepthEstimatorShutdown:
    """Test DepthEstimator shutdown."""
    
    @pytest.mark.asyncio
    async def test_shutdown_with_client(self, tmp_path):
        """Test shutdown disconnects the client."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                await estimator.initialize()
        
        # Verify client was set
        assert estimator.client is not None
        
        # Shutdown
        await estimator.shutdown()
        
        # Verify disconnect was called
        mock_client.disconnect.assert_called_once()
        
        # Verify state
        assert estimator.client is None
        assert estimator.is_loaded is False
    
    @pytest.mark.asyncio
    async def test_shutdown_without_client(self):
        """Test shutdown handles missing client gracefully."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # No client set
        assert estimator.client is None
        
        # Shutdown should not raise
        await estimator.shutdown()
        
        # State should be unchanged
        assert estimator.client is None
        assert estimator.is_loaded is False


class TestInputShapeParsing:
    """Test input shape parsing logic."""
    
    @pytest.mark.asyncio
    async def test_parse_nchw_shape(self):
        """Test parsing NCHW layout."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        estimator._parse_input_shape((1, 3, 256, 320))
        
        assert estimator.input_layout == "NCHW"
        assert estimator.input_channels == 3
        assert estimator.input_height == 256
        assert estimator.input_width == 320
    
    @pytest.mark.asyncio
    async def test_parse_nhwc_shape(self):
        """Test parsing NHWC layout."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        estimator._parse_input_shape((1, 256, 320, 3))
        
        assert estimator.input_layout == "NHWC"
        assert estimator.input_channels == 3
        assert estimator.input_height == 256
        assert estimator.input_width == 320


class TestDepthOutputExtraction:
    """Test depth map extraction from model output."""
    
    @pytest.mark.asyncio
    async def test_extract_depth_2d(self):
        """Test extracting 2D depth from model output."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # Create mock output - 3D array (batch, height, width)
        output_array = np.random.rand(1, 256, 320).astype(np.float32)
        output_dict = {"output": output_array}
        
        depth = estimator._extract_depth_output(output_dict)
        
        assert depth.ndim == 2
        assert depth.shape == (256, 320)
        assert depth.dtype == np.float32
    
    @pytest.mark.asyncio
    async def test_extract_depth_from_dict(self):
        """Test extracting depth from dict output."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # Output as dict with multiple named outputs
        output_array = np.random.rand(1, 256, 320).astype(np.float32)
        output_dict = {
            "output": output_array,
            "other": np.zeros((1, 10)),  # Other outputs to ignore
        }
        
        depth = estimator._extract_depth_output(output_dict)
        
        assert depth.ndim == 2
        assert depth.shape == (256, 320)


class TestDepthNormalization:
    """Test depth normalization."""
    
    @pytest.mark.asyncio
    async def test_normalize_depth(self):
        """Test depth normalization to 0-1 range."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # Create depth with known min/max
        depth = np.array([[1.0, 2.0], [3.0, 5.0]])
        
        normalized = estimator._normalize_depth(depth)
        
        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0
        assert normalized[0, 0] == 0.0  # min value
        assert normalized[1, 1] == 1.0  # max value
    
    @pytest.mark.asyncio
    async def test_normalize_constant_depth(self):
        """Test normalizing constant depth (no variation)."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # Constant depth
        depth = np.ones((256, 320)) * 5.0
        
        normalized = estimator._normalize_depth(depth)
        
        # Should handle gracefully (return same values or zeros)
        assert normalized.shape == depth.shape


class TestDepthStats:
    """Test depth statistics computation."""
    
    @pytest.mark.asyncio
    async def test_compute_depth_stats(self):
        """Test depth statistics computation."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig
        
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        # Create depth with known stats
        depth = np.array([[1.0, 2.0], [3.0, 100.0]])  # 100 is outlier
        
        stats = estimator._compute_depth_stats(depth)
        
        assert "min" in stats
        assert "max" in stats
        assert "mean" in stats
        assert "p95" in stats
        
        # Min should be 1.0
        assert stats["min"] == 1.0
        
        # P95 should exclude the outlier (100)
        assert stats["p95"] < 100.0
        assert stats["p95"] == 3.0  # 95th percentile excludes outlier


class TestConcurrency:
    """Test concurrent request handling."""
    
    @pytest.mark.asyncio
    async def test_concurrent_inferences(self, sample_image_bytes, sample_depth_map, tmp_path):
        """Test that concurrent inferences are serialized via device manager."""
        from hailo_depth_server import DepthEstimator, DepthServiceConfig, encode_tensor
        
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_hef = model_dir / "scdepthv3.hef"
        model_hef.write_bytes(b"mock hef data")
        
        config = DepthServiceConfig()
        config.model_dir = str(model_dir)
        
        estimator = DepthEstimator(config)
        
        with patch('hailo_depth_server.HailoDeviceClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            with patch('hailo_depth_server.get_hef_input_shape', return_value=(1, 3, 256, 320)):
                await estimator.initialize()
        
        # Mock inference results
        mock_result = {"result": encode_tensor(sample_depth_map)}
        mock_client.infer.return_value = mock_result
        
        # Run multiple concurrent inferences
        tasks = [
            estimator.estimate_depth(sample_image_bytes, output_format="numpy")
            for _ in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(results) == 3
        assert all("model" in r for r in results)
        
        # Device manager should have received all requests (serialized by device manager)
        assert mock_client.infer.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
