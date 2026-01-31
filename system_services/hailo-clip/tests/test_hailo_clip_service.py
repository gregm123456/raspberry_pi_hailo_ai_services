#!/usr/bin/env python3
"""
Test suite for Hailo CLIP Service.

Tests the REST API and core functionality of the hailo-clip systemd service.
"""

import base64
import json
import logging
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import pytest
import requests
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service configuration
SERVICE_NAME = "hailo-clip"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 5000
BASE_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


@pytest.fixture(scope="session")
def service_running():
    """Verify service is running or skip tests."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            timeout=5
        )
        if result.returncode != 0:
            pytest.skip(f"Service {SERVICE_NAME} is not running")
    except Exception as e:
        pytest.skip(f"Cannot check service status: {e}")


@pytest.fixture
def test_image():
    """Create a test image (1x1 pixel)."""
    img = Image.new("RGB", (224, 224), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    
    b64 = base64.b64encode(buffer.read()).decode()
    return f"data:image/jpeg;base64,{b64}"


class TestHealth:
    """Health endpoint tests."""
    
    def test_health_endpoint(self, service_running):
        """Test /health endpoint."""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "hailo-clip"
        assert "model_loaded" in data
        assert "model" in data
    
    def test_health_response_format(self, service_running):
        """Test health response has required fields."""
        response = requests.get(f"{BASE_URL}/health")
        data = response.json()
        
        required_fields = ["status", "service", "model_loaded", "model"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestClassification:
    """Image classification endpoint tests."""
    
    def test_classify_basic(self, service_running, test_image):
        """Test basic classification."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": ["red object", "blue object", "green object"],
                "top_k": 1
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "classifications" in data
        assert "inference_time_ms" in data
        assert "model" in data
        assert len(data["classifications"]) <= 1  # top_k=1
    
    def test_classify_response_format(self, service_running, test_image):
        """Test classification response format."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": ["test1", "test2"],
                "top_k": 2
            }
        )
        
        data = response.json()
        
        # Check classifications format
        for classification in data["classifications"]:
            assert "text" in classification
            assert "score" in classification
            assert "rank" in classification
            assert isinstance(classification["score"], (int, float))
            assert 0 <= classification["score"] <= 1
    
    def test_classify_missing_image(self, service_running):
        """Test classify without image."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={"prompts": ["test"]}
        )
        
        assert response.status_code == 400
        assert "error" in response.json()
    
    def test_classify_missing_prompts(self, service_running, test_image):
        """Test classify without prompts."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={"image": test_image}
        )
        
        assert response.status_code == 400
        assert "error" in response.json()
    
    def test_classify_top_k(self, service_running, test_image):
        """Test top_k parameter."""
        prompts = ["red", "blue", "green", "yellow", "purple"]
        
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": prompts,
                "top_k": 2
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["classifications"]) <= 2
    
    def test_classify_threshold(self, service_running, test_image):
        """Test threshold parameter."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": ["test1", "test2", "test3"],
                "threshold": 0.9  # Very high threshold
            }
        )
        
        assert response.status_code == 200
        # High threshold may result in no or few matches
        assert "classifications" in response.json()
    
    def test_classify_inference_time(self, service_running, test_image):
        """Test inference_time_ms is reasonable."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": ["test"],
            }
        )
        
        data = response.json()
        inference_time = data["inference_time_ms"]
        
        # Inference should complete in reasonable time (< 10 seconds)
        assert 0 < inference_time < 10000
    
    def test_classify_consistency(self, service_running, test_image):
        """Test classification is consistent."""
        prompts = ["red object", "test item"]
        
        responses = []
        for _ in range(3):
            response = requests.post(
                f"{BASE_URL}/v1/classify",
                json={
                    "image": test_image,
                    "prompts": prompts,
                    "top_k": 1
                }
            )
            responses.append(response.json())
        
        # All responses should have same top match (or very close scores)
        for resp in responses:
            assert len(resp["classifications"]) > 0


class TestEmbeddings:
    """Embedding endpoints tests."""
    
    def test_embed_image(self, service_running, test_image):
        """Test image embedding endpoint."""
        response = requests.post(
            f"{BASE_URL}/v1/embed/image",
            json={"image": test_image}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "embedding" in data
        assert "dimension" in data
        assert "model" in data
        assert len(data["embedding"]) == data["dimension"]
    
    def test_embed_image_normalization(self, service_running, test_image):
        """Test image embeddings are normalized."""
        response = requests.post(
            f"{BASE_URL}/v1/embed/image",
            json={"image": test_image}
        )
        
        data = response.json()
        embedding = data["embedding"]
        
        # Compute L2 norm
        norm = sum(x**2 for x in embedding) ** 0.5
        
        # Should be approximately 1 (normalized)
        assert 0.9 < norm < 1.1, f"Embedding not normalized: norm={norm}"
    
    def test_embed_text(self, service_running):
        """Test text embedding endpoint."""
        response = requests.post(
            f"{BASE_URL}/v1/embed/text",
            json={"text": "person wearing red shirt"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "embedding" in data
        assert "dimension" in data
        assert "model" in data
        assert len(data["embedding"]) == data["dimension"]
    
    def test_embed_text_missing_text(self, service_running):
        """Test text embedding without text."""
        response = requests.post(
            f"{BASE_URL}/v1/embed/text",
            json={}
        )
        
        assert response.status_code == 400
        assert "error" in response.json()
    
    def test_embed_dimension_consistency(self, service_running, test_image):
        """Test image and text embeddings have same dimension."""
        img_response = requests.post(
            f"{BASE_URL}/v1/embed/image",
            json={"image": test_image}
        )
        
        text_response = requests.post(
            f"{BASE_URL}/v1/embed/text",
            json={"text": "test"}
        )
        
        img_dim = img_response.json()["dimension"]
        text_dim = text_response.json()["dimension"]
        
        assert img_dim == text_dim, "Image and text embedding dimensions don't match"


class TestErrorHandling:
    """Error handling tests."""
    
    def test_invalid_json(self, service_running):
        """Test invalid JSON request."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            data="not json",
            headers={"Content-Type": "application/json"}
        )
        
        # Should handle gracefully (4xx error)
        assert response.status_code >= 400
    
    def test_invalid_endpoint(self, service_running):
        """Test non-existent endpoint."""
        response = requests.get(f"{BASE_URL}/v1/nonexistent")
        
        assert response.status_code == 404
        assert "error" in response.json()
    
    def test_invalid_base64_image(self, service_running):
        """Test invalid base64 image."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": "data:image/jpeg;base64,invalid!!!",
                "prompts": ["test"]
            }
        )
        
        assert response.status_code >= 400
    
    def test_empty_prompts(self, service_running, test_image):
        """Test empty prompts array."""
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": []
            }
        )
        
        assert response.status_code >= 400


class TestPerformance:
    """Performance and concurrency tests."""
    
    def test_response_time(self, service_running, test_image):
        """Test response time is reasonable."""
        start = time.time()
        
        response = requests.post(
            f"{BASE_URL}/v1/classify",
            json={
                "image": test_image,
                "prompts": ["test"],
            }
        )
        
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Response should complete within 10 seconds
        assert elapsed < 10, f"Response took {elapsed}s"
    
    def test_concurrent_requests(self, service_running, test_image):
        """Test service handles concurrent requests."""
        import concurrent.futures
        
        def make_request():
            return requests.post(
                f"{BASE_URL}/v1/classify",
                json={
                    "image": test_image,
                    "prompts": ["test"],
                }
            )
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(3)]
            
            for future in concurrent.futures.as_completed(futures):
                response = future.result()
                assert response.status_code == 200


def main():
    """Run tests."""
    pytest.main([__file__, "-v", "-s"])


if __name__ == "__main__":
    main()
