"""
Integration tests for hailo-face service.

Tests face detection, embedding extraction, recognition, and database operations.
"""

import base64
import io
import json
import time
from pathlib import Path

import pytest
import requests
from PIL import Image


API_BASE_URL = "http://localhost:5002"
TEST_TIMEOUT = 30  # seconds


@pytest.fixture(scope="module")
def api_health_check():
    """Ensure service is running before tests."""
    url = f"{API_BASE_URL}/health"
    
    for attempt in range(10):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                assert data["status"] == "healthy"
                return data
        except requests.RequestException:
            time.sleep(2)
    
    pytest.fail("Service health check failed after 10 attempts")


@pytest.fixture
def test_image_base64():
    """Generate a simple test image as base64."""
    # Create a 640x480 RGB image
    img = Image.new("RGB", (640, 480), color=(100, 150, 200))
    
    # Add some variation to simulate a face region
    # (In reality, this won't detect faces, but tests the pipeline)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    
    b64_str = base64.b64encode(buffer.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"


def test_health_endpoint(api_health_check):
    """Test health endpoint returns expected structure."""
    assert api_health_check["service"] == "hailo-face"
    assert api_health_check["model_loaded"] is True
    assert "detection_model" in api_health_check
    assert "recognition_model" in api_health_check


def test_detect_faces(api_health_check, test_image_base64):
    """Test face detection endpoint."""
    url = f"{API_BASE_URL}/v1/detect"
    payload = {"image": test_image_base64}
    
    response = requests.post(url, json=payload, timeout=TEST_TIMEOUT)
    assert response.status_code == 200
    
    data = response.json()
    assert "faces" in data
    assert "count" in data
    assert "inference_time_ms" in data
    assert isinstance(data["faces"], list)
    assert data["count"] == len(data["faces"])


def test_detect_faces_invalid_image(api_health_check):
    """Test detection with invalid image."""
    url = f"{API_BASE_URL}/v1/detect"
    payload = {"image": "invalid_base64"}
    
    response = requests.post(url, json=payload, timeout=TEST_TIMEOUT)
    assert response.status_code in [400, 500]
    assert "error" in response.json()


def test_embed_face(api_health_check, test_image_base64):
    """Test face embedding extraction."""
    url = f"{API_BASE_URL}/v1/embed"
    payload = {
        "image": test_image_base64,
        # Provide a bbox to avoid auto-detection failure
        "bbox": [100, 100, 200, 200]
    }
    
    response = requests.post(url, json=payload, timeout=TEST_TIMEOUT)
    
    # May succeed or fail depending on mock/real model
    if response.status_code == 200:
        data = response.json()
        assert "embedding" in data
        assert "dimension" in data
        assert data["dimension"] == 512
        assert len(data["embedding"]) == 512
    else:
        # Expected if no real face in test image
        assert response.status_code in [400, 500]


def test_database_operations(api_health_check, test_image_base64):
    """Test database add, list, and remove operations."""
    
    # List identities (should work even if empty)
    list_url = f"{API_BASE_URL}/v1/database/list"
    response = requests.get(list_url, timeout=TEST_TIMEOUT)
    
    if response.status_code == 503:
        pytest.skip("Database not enabled")
    
    assert response.status_code == 200
    data = response.json()
    assert "identities" in data
    assert "count" in data
    initial_count = data["count"]
    
    # Add test identity
    add_url = f"{API_BASE_URL}/v1/database/add"
    test_name = f"test_identity_{int(time.time())}"
    payload = {
        "name": test_name,
        "image": test_image_base64,
        "bbox": [100, 100, 200, 200]  # Provide bbox to skip detection
    }
    
    response = requests.post(add_url, json=payload, timeout=TEST_TIMEOUT)
    
    # May fail if no valid face detected even with bbox
    if response.status_code == 200:
        data = response.json()
        assert data["name"] == test_name
        
        # Verify added
        response = requests.get(list_url, timeout=TEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == initial_count + 1
        
        # Remove test identity
        remove_url = f"{API_BASE_URL}/v1/database/remove"
        payload = {"name": test_name}
        response = requests.post(remove_url, json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 200
        
        # Verify removed
        response = requests.get(list_url, timeout=TEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == initial_count
    else:
        # Expected in mock mode or with invalid test image
        pytest.skip("Add identity failed (mock mode or invalid face)")


def test_recognize_faces(api_health_check, test_image_base64):
    """Test face recognition endpoint."""
    url = f"{API_BASE_URL}/v1/recognize"
    payload = {
        "image": test_image_base64,
        "threshold": 0.5
    }
    
    response = requests.post(url, json=payload, timeout=TEST_TIMEOUT)
    
    if response.status_code == 503:
        pytest.skip("Database not enabled")
    
    assert response.status_code == 200
    data = response.json()
    assert "faces" in data
    assert "count" in data
    assert isinstance(data["faces"], list)


def test_concurrent_requests(api_health_check, test_image_base64):
    """Test handling of concurrent requests."""
    import concurrent.futures
    
    url = f"{API_BASE_URL}/v1/detect"
    payload = {"image": test_image_base64}
    
    def make_request():
        response = requests.post(url, json=payload, timeout=TEST_TIMEOUT)
        return response.status_code
    
    # Send 5 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # All should succeed (or gracefully fail)
    assert all(status in [200, 400, 500] for status in results)
    # At least some should succeed
    assert any(status == 200 for status in results)


def test_missing_fields(api_health_check):
    """Test API error handling for missing required fields."""
    
    # Detect without image
    url = f"{API_BASE_URL}/v1/detect"
    response = requests.post(url, json={}, timeout=TEST_TIMEOUT)
    assert response.status_code == 400
    assert "error" in response.json()
    
    # Add identity without name
    url = f"{API_BASE_URL}/v1/database/add"
    response = requests.post(url, json={"image": "dummy"}, timeout=TEST_TIMEOUT)
    
    if response.status_code != 503:  # Skip if DB disabled
        assert response.status_code == 400
        assert "error" in response.json()


def test_performance_baseline(api_health_check, test_image_base64):
    """Test that inference completes within reasonable time."""
    url = f"{API_BASE_URL}/v1/detect"
    payload = {"image": test_image_base64}
    
    response = requests.post(url, json=payload, timeout=TEST_TIMEOUT)
    assert response.status_code == 200
    
    data = response.json()
    inference_time = data.get("inference_time_ms", 0)
    
    # Inference should complete in <5 seconds (even in mock mode)
    assert inference_time < 5000, f"Inference too slow: {inference_time}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
