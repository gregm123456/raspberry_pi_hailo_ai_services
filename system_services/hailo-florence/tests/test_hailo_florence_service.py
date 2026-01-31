#!/usr/bin/env python3
"""
Integration tests for hailo-florence service.

Tests the Florence-2 image captioning API endpoints.
"""

import os
import sys
import time
import base64
import pytest
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO


# Configuration
API_BASE = os.getenv('FLORENCE_API_BASE', 'http://localhost:8082')
SERVICE_NAME = 'hailo-florence'


@pytest.fixture(scope="session")
def api_base():
    """API base URL."""
    return API_BASE


@pytest.fixture(scope="session")
def test_image_b64():
    """Create a test image and encode as base64."""
    # Create 100x100 RGB image with red color
    img = Image.new('RGB', (100, 100), color='red')
    
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return f"data:image/jpeg;base64,{b64_data}"


@pytest.fixture(scope="session")
def service_ready(api_base):
    """Wait for service to be ready before running tests."""
    max_retries = 30
    retry_delay = 2
    
    for i in range(max_retries):
        try:
            response = requests.get(f"{api_base}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('model_loaded', False):
                    print(f"\n✓ Service ready after {i * retry_delay}s")
                    return True
        except requests.exceptions.RequestException:
            pass
        
        if i < max_retries - 1:
            print(f"Waiting for service... ({i+1}/{max_retries})")
            time.sleep(retry_delay)
    
    pytest.fail("Service did not become ready within timeout")


class TestHealthEndpoint:
    """Tests for /health endpoint."""
    
    def test_health_endpoint_accessible(self, api_base, service_ready):
        """Test that health endpoint is accessible."""
        response = requests.get(f"{api_base}/health")
        assert response.status_code == 200
    
    def test_health_response_format(self, api_base, service_ready):
        """Test health response has correct format."""
        response = requests.get(f"{api_base}/health")
        data = response.json()
        
        assert 'status' in data
        assert 'model_loaded' in data
        assert 'uptime_seconds' in data
        assert 'version' in data
        assert 'hailo_device' in data
    
    def test_health_model_loaded(self, api_base, service_ready):
        """Test that model is loaded."""
        response = requests.get(f"{api_base}/health")
        data = response.json()
        
        assert data['model_loaded'] is True
        assert data['status'] == 'healthy'


class TestCaptionEndpoint:
    """Tests for /v1/caption endpoint."""
    
    def test_caption_basic_request(self, api_base, test_image_b64, service_ready):
        """Test basic caption generation."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={"image": test_image_b64}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'caption' in data
        assert 'inference_time_ms' in data
        assert 'model' in data
        assert 'token_count' in data
        
        assert len(data['caption']) > 0
        assert data['inference_time_ms'] > 0
        assert data['model'] == 'florence-2'
    
    def test_caption_with_params(self, api_base, test_image_b64, service_ready):
        """Test caption generation with custom parameters."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={
                "image": test_image_b64,
                "max_length": 50,
                "min_length": 20,
                "temperature": 0.5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data['caption']) > 0
    
    def test_caption_missing_image(self, api_base, service_ready):
        """Test error when image is missing."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_caption_invalid_image_format(self, api_base, service_ready):
        """Test error with invalid image format."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={"image": "not_a_valid_image"}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_caption_invalid_base64(self, api_base, service_ready):
        """Test error with malformed base64."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={"image": "data:image/jpeg;base64,INVALID!!!"}
        )
        
        assert response.status_code == 400  # Bad request
    
    def test_caption_invalid_max_length(self, api_base, test_image_b64, service_ready):
        """Test error with invalid max_length."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={
                "image": test_image_b64,
                "max_length": 500  # Exceeds limit
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_caption_max_less_than_min(self, api_base, test_image_b64, service_ready):
        """Test error when max_length < min_length."""
        response = requests.post(
            f"{api_base}/v1/caption",
            json={
                "image": test_image_b64,
                "max_length": 20,
                "min_length": 50
            }
        )
        
        assert response.status_code == 422  # Validation error


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""
    
    def test_metrics_endpoint_accessible(self, api_base, service_ready):
        """Test that metrics endpoint is accessible."""
        response = requests.get(f"{api_base}/metrics")
        assert response.status_code == 200
    
    def test_metrics_response_format(self, api_base, service_ready):
        """Test metrics response has correct format."""
        response = requests.get(f"{api_base}/metrics")
        data = response.json()
        
        required_fields = [
            'requests_total',
            'requests_succeeded',
            'requests_failed',
            'average_inference_time_ms',
            'p50_inference_time_ms',
            'p95_inference_time_ms',
            'p99_inference_time_ms',
            'memory_usage_mb',
            'model_cache_hit_rate',
            'uptime_seconds'
        ]
        
        for field in required_fields:
            assert field in data
    
    def test_metrics_increment_after_request(self, api_base, test_image_b64, service_ready):
        """Test that metrics increment after requests."""
        # Get initial metrics
        response1 = requests.get(f"{api_base}/metrics")
        metrics1 = response1.json()
        initial_total = metrics1['requests_total']
        
        # Make a caption request
        requests.post(
            f"{api_base}/v1/caption",
            json={"image": test_image_b64}
        )
        
        # Get updated metrics
        response2 = requests.get(f"{api_base}/metrics")
        metrics2 = response2.json()
        
        assert metrics2['requests_total'] > initial_total


class TestPerformance:
    """Performance tests."""
    
    def test_caption_latency(self, api_base, test_image_b64, service_ready):
        """Test that caption generation latency is reasonable."""
        start_time = time.time()
        
        response = requests.post(
            f"{api_base}/v1/caption",
            json={"image": test_image_b64}
        )
        
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        assert response.status_code == 200
        
        # Latency should be under 3 seconds (generous for test env)
        assert latency_ms < 3000, f"Latency too high: {latency_ms}ms"
        
        # Check reported inference time
        data = response.json()
        assert data['inference_time_ms'] < 2000, \
            f"Inference time too high: {data['inference_time_ms']}ms"
    
    def test_sequential_requests(self, api_base, test_image_b64, service_ready):
        """Test multiple sequential requests."""
        num_requests = 3
        
        for i in range(num_requests):
            response = requests.post(
                f"{api_base}/v1/caption",
                json={"image": test_image_b64}
            )
            
            assert response.status_code == 200, \
                f"Request {i+1}/{num_requests} failed"


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_large_image_rejected(self, api_base, service_ready):
        """Test that very large images are rejected."""
        # Create a 5000x5000 image (very large)
        large_img = Image.new('RGB', (5000, 5000), color='blue')
        buffer = BytesIO()
        large_img.save(buffer, format='JPEG', quality=95)
        b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        response = requests.post(
            f"{api_base}/v1/caption",
            json={"image": f"data:image/jpeg;base64,{b64_data}"}
        )
        
        # Should reject (413 Payload Too Large) or accept and process
        assert response.status_code in [200, 413]
    
    def test_grayscale_image_handled(self, api_base, service_ready):
        """Test that grayscale images are handled correctly."""
        # Create grayscale image
        gray_img = Image.new('L', (100, 100), color=128)
        buffer = BytesIO()
        gray_img.save(buffer, format='JPEG')
        b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        response = requests.post(
            f"{api_base}/v1/caption",
            json={"image": f"data:image/jpeg;base64,{b64_data}"}
        )
        
        # Should either convert and succeed, or reject gracefully
        assert response.status_code in [200, 400]


def test_service_info():
    """Print service information."""
    print("\n" + "="*60)
    print("hailo-florence Service Test Suite")
    print("="*60)
    print(f"API Base URL: {API_BASE}")
    print(f"Service Name: {SERVICE_NAME}")
    print("="*60 + "\n")


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v', '--tb=short'])
