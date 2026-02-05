"""
Integration tests for hailo-depth service.

Run with: pytest test_hailo_depth_service.py -v
"""

import base64
import io
import json
import requests
import numpy as np
from PIL import Image
import pytest
import time


# Test configuration
BASE_URL = "http://localhost:11436"
TIMEOUT = 30


@pytest.fixture(scope="module")
def service_url():
    """Base URL for the service."""
    return BASE_URL


@pytest.fixture(scope="module")
def wait_for_service(service_url):
    """Wait for service to be ready before running tests."""
    max_wait = 30
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(f"{service_url}/health/ready", timeout=2)
            if response.status_code == 200 and response.json().get("ready"):
                print(f"\nService ready after {time.time() - start:.1f}s")
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    
    pytest.fail("Service did not become ready within timeout")


@pytest.fixture
def sample_image():
    """Generate a sample test image."""
    # Create 640x480 RGB gradient image
    width, height = 640, 480
    img_array = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Create gradient
    for y in range(height):
        for x in range(width):
            img_array[y, x] = [int(x * 255 / width), int(y * 255 / height), 128]
    
    img = Image.fromarray(img_array)
    
    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=90)
    buffer.seek(0)
    
    return buffer.read()


class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health(self, service_url, wait_for_service):
        """Test /health endpoint."""
        response = requests.get(f"{service_url}/health", timeout=TIMEOUT)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "ok"
        assert data["service"] == "hailo-depth"
        assert "model" in data
        assert "model_type" in data
        assert isinstance(data["uptime_seconds"], (int, float))
    
    def test_health_ready(self, service_url, wait_for_service):
        """Test /health/ready endpoint."""
        response = requests.get(f"{service_url}/health/ready", timeout=TIMEOUT)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ready"] is True
    
    def test_service_info(self, service_url, wait_for_service):
        """Test /v1/info endpoint."""
        response = requests.get(f"{service_url}/v1/info", timeout=TIMEOUT)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["service"] == "hailo-depth"
        assert "version" in data
        assert "model" in data
        assert "capabilities" in data
        assert data["capabilities"]["monocular"] is True
        assert "output_formats" in data["capabilities"]
        assert "colormaps" in data["capabilities"]


class TestDepthEstimation:
    """Test depth estimation inference."""
    
    def test_estimate_multipart_both(self, service_url, wait_for_service, sample_image):
        """Test depth estimation with multipart form (output=both)."""
        files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
        data = {
            'output_format': 'both',
            'normalize': 'true',
            'colormap': 'viridis'
        }
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            data=data,
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Check response structure
        assert result["model"] == "scdepthv3"
        assert result["model_type"] == "monocular"
        assert "input_shape" in result
        assert "depth_shape" in result
        assert "inference_time_ms" in result
        assert result["normalized"] is True
        
        # Check outputs
        assert "depth_map" in result
        assert "depth_image" in result
        
        # Verify depth_map (NumPy)
        npz_bytes = base64.b64decode(result["depth_map"])
        npz_buffer = io.BytesIO(npz_bytes)
        depth_array = np.load(npz_buffer)['depth']
        assert depth_array.shape == tuple(result["depth_shape"])
        assert depth_array.dtype == np.float32
        
        # Verify depth_image (PNG)
        png_bytes = base64.b64decode(result["depth_image"])
        png_buffer = io.BytesIO(png_bytes)
        depth_img = Image.open(png_buffer)
        assert depth_img.format == 'PNG'
        assert depth_img.mode == 'RGB'
    
    def test_estimate_json_base64(self, service_url, wait_for_service, sample_image):
        """Test depth estimation with JSON and base64-encoded image."""
        image_b64 = base64.b64encode(sample_image).decode('utf-8')
        
        payload = {
            'image': image_b64,
            'output_format': 'numpy',
            'normalize': True
        }
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            json=payload,
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["model"] == "scdepthv3"
        assert "depth_map" in result
        assert "depth_image" not in result  # Only numpy requested
    
    def test_estimate_image_only(self, service_url, wait_for_service, sample_image):
        """Test depth estimation with output_format=image."""
        files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
        data = {'output_format': 'image', 'colormap': 'plasma'}
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            data=data,
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert "depth_image" in result
        assert "depth_map" not in result  # Only image requested
    
    def test_estimate_different_colormaps(self, service_url, wait_for_service, sample_image):
        """Test depth estimation with different colormaps."""
        colormaps = ['viridis', 'plasma', 'magma', 'turbo', 'jet']
        
        for colormap in colormaps:
            files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
            data = {'output_format': 'image', 'colormap': colormap}
            
            response = requests.post(
                f"{service_url}/v1/depth/estimate",
                files=files,
                data=data,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200, f"Failed for colormap: {colormap}"
            result = response.json()
            assert "depth_image" in result


class TestErrorHandling:
    """Test error handling and validation."""
    
    def test_missing_image(self, service_url, wait_for_service):
        """Test request without image field."""
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            json={'output_format': 'numpy'},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 400
        error = response.json()
        assert "error" in error
        assert "message" in error["error"]
    
    def test_invalid_image_data(self, service_url, wait_for_service):
        """Test with invalid image data."""
        files = {'image': ('test.txt', b'not an image', 'text/plain')}
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            timeout=TIMEOUT
        )
        
        assert response.status_code == 500
        error = response.json()
        assert "error" in error
    
    def test_invalid_content_type(self, service_url, wait_for_service):
        """Test with unsupported content type."""
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            data="plain text",
            headers={'Content-Type': 'text/plain'},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 400
        error = response.json()
        assert "error" in error
        assert "content type" in error["error"]["message"].lower()


class TestPerformance:
    """Test performance characteristics."""
    
    def test_inference_time(self, service_url, wait_for_service, sample_image):
        """Test that inference completes within reasonable time."""
        files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
        data = {'output_format': 'numpy'}
        
        start = time.time()
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            data=data,
            timeout=TIMEOUT
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        result = response.json()
        
        # Check inference time
        inference_ms = result["inference_time_ms"]
        assert inference_ms > 0
        assert inference_ms < 5000, f"Inference too slow: {inference_ms}ms"
        
        # Check total time (including network)
        assert elapsed < 10, f"Total request time too slow: {elapsed}s"
    
    def test_sequential_requests(self, service_url, wait_for_service, sample_image):
        """Test multiple sequential requests."""
        num_requests = 5
        times = []
        
        for i in range(num_requests):
            files = {'image': (f'test{i}.jpg', sample_image, 'image/jpeg')}
            data = {'output_format': 'numpy'}
            
            response = requests.post(
                f"{service_url}/v1/depth/estimate",
                files=files,
                data=data,
                timeout=TIMEOUT
            )
            
            assert response.status_code == 200
            result = response.json()
            times.append(result["inference_time_ms"])
        
        # Check that times are consistent (no major degradation)
        avg_time = sum(times) / len(times)
        assert all(t < avg_time * 2 for t in times), f"Inconsistent times: {times}"


class TestNewFeatures:
    """Test Phase 4 enhancements: stats, 16-bit PNG, image URLs."""
    
    def test_depth_stats_output(self, service_url, wait_for_service, sample_image):
        """Test that depth statistics are included in response."""
        files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
        data = {'output_format': 'numpy'}
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            data=data,
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Check stats are present
        assert "stats" in result
        stats = result["stats"]
        
        assert "min" in stats
        assert "max" in stats
        assert "mean" in stats
        assert "p95" in stats
        
        # Verify stats values are reasonable
        assert stats["min"] <= stats["mean"] <= stats["max"]
        assert stats["mean"] <= stats["p95"] <= stats["max"]
    
    def test_depth_png_16_output(self, service_url, wait_for_service, sample_image):
        """Test 16-bit PNG depth output format."""
        files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
        data = {'output_format': 'depth_png_16'}
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            data=data,
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Check 16-bit PNG is present
        assert "depth_png_16" in result
        assert "depth_map" not in result
        assert "depth_image" not in result
        
        # Verify it's valid PNG data (base64)
        try:
            png_bytes = base64.b64decode(result["depth_png_16"])
            # Check PNG magic number
            assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'
        except Exception as e:
            pytest.fail(f"Invalid PNG data: {e}")
    
    def test_image_url_input(self, service_url, wait_for_service, sample_image):
        """Test image_url input (if service allows it)."""
        # Note: This test requires a publicly accessible image URL
        # For now, we test the request format validation
        
        response = requests.post(
            f"{service_url}/v1/depth/estimate",
            json={
                'image_url': 'https://example.com/nonexistent.jpg',
                'output_format': 'numpy'
            },
            timeout=TIMEOUT
        )
        
        # Either succeeds (if image fetched) or returns 400 (if URL fetch failed)
        # We're mainly testing that image_url field is accepted
        assert response.status_code in [200, 400]
        
        if response.status_code == 400:
            error = response.json()
            assert "error" in error
            # Should contain message about fetching image
    
    def test_model_list_endpoint(self, service_url, wait_for_service):
        """Test /v1/models endpoint."""
        response = requests.get(f"{service_url}/v1/models", timeout=TIMEOUT)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "models" in data
        assert len(data["models"]) > 0
        
        # Check model info structure
        model = data["models"][0]
        assert "name" in model
        assert "type" in model
        assert "description" in model
    
    def test_inference_count_tracking(self, service_url, wait_for_service, sample_image):
        """Test that inference count is tracked in health endpoint."""
        # Get baseline count
        health1 = requests.get(f"{service_url}/health", timeout=TIMEOUT).json()
        count1 = health1.get("inference_count", 0)
        
        # Run an inference
        files = {'image': ('test.jpg', sample_image, 'image/jpeg')}
        requests.post(
            f"{service_url}/v1/depth/estimate",
            files=files,
            timeout=TIMEOUT
        )
        
        # Check count increased
        health2 = requests.get(f"{service_url}/health", timeout=TIMEOUT).json()
        count2 = health2.get("inference_count", 0)
        
        assert count2 > count1, "Inference count should increase after inference"


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "slow: marks tests as slow")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
