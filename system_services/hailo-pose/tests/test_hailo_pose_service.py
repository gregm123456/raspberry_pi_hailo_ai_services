"""
Integration tests for hailo-pose service
"""

import pytest
import requests
import base64
import json
from pathlib import Path
from typing import Dict, Any
import time


BASE_URL = "http://localhost:11436"
SERVICE_NAME = "hailo-pose"


@pytest.fixture(scope="module")
def service_url() -> str:
    """Get service base URL."""
    return BASE_URL


@pytest.fixture(scope="module")
def sample_image() -> bytes:
    """Create a minimal valid JPEG image for testing."""
    # Minimal 1x1 JPEG (valid image data)
    # This is a base64-encoded 1x1 red pixel JPEG
    minimal_jpeg_b64 = (
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAIBAQIBAQICAgICAgICAwUDAwMD"
        "AwYEBAMFBwYHBwcGBwcICQsJCAgKCAcHCg0KCgsMDAwMBwkODw0MDgsMDAz/"
        "2wBDAQICAgMDAwYDAwYMCAcIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwM"
        "DAwMDAwMDAwMDAwMDAwMDAwMDAwMDAz/wAARCAABAAEDASIAAhEBAxEB/8QA"
        "HQAAAAEZBQEAAAAAAAAAAAAAAAEHCAMECQQBBQYHAP/EAB8QAAEEAgIDAQAA"
        "AAAAAAAAAAEAAgMEBQYHERITITH/xAAZAQEBAQEBAQAAAAAAAAAAAAAAAwEE"
        "AgUG/8QAIREBAAEDBAIDAAAAAAAAAAAAAQARAgMhMRIxQQRRYXGh/9oADAMB"
        "AAIRAxEAPwDyrqOoahqU7Mx2YtY7R47lGMz9VJK+R7m6qx5Y1oJIhAJPQABJ"
        "JPygCNz08WA//9k="
    )
    return base64.b64decode(minimal_jpeg_b64)


@pytest.fixture(scope="module")
def sample_image_b64(sample_image: bytes) -> str:
    """Base64-encoded sample image."""
    return base64.b64encode(sample_image).decode('utf-8')


class TestServiceHealth:
    """Test service health and availability."""
    
    def test_health_endpoint(self, service_url: str):
        """Test /health endpoint."""
        response = requests.get(f"{service_url}/health", timeout=5)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        assert "model" in data
        assert "model_loaded" in data
        assert "uptime_seconds" in data
    
    def test_readiness_endpoint(self, service_url: str):
        """Test /health/ready endpoint."""
        response = requests.get(f"{service_url}/health/ready", timeout=5)
        
        # Should be 200 (ready) or 503 (not ready yet)
        assert response.status_code in [200, 503]
        
        data = response.json()
        assert "ready" in data
        
        if response.status_code == 200:
            assert data["ready"] is True
        else:
            assert data["ready"] is False
            assert "reason" in data
    
    def test_models_endpoint(self, service_url: str):
        """Test /v1/models endpoint."""
        response = requests.get(f"{service_url}/v1/models", timeout=5)
        assert response.status_code == 200
        
        data = response.json()
        assert "data" in data
        assert "object" in data
        assert data["object"] == "list"
        
        # Should have at least one model
        assert len(data["data"]) > 0
        
        model = data["data"][0]
        assert "id" in model
        assert "object" in model
        assert model["object"] == "model"
        assert "task" in model
        assert model["task"] == "pose-estimation"


class TestPoseDetection:
    """Test pose detection inference."""
    
    def test_detect_multipart(self, service_url: str, sample_image: bytes):
        """Test /v1/pose/detect with multipart/form-data."""
        files = {"image": ("test.jpg", sample_image, "image/jpeg")}
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            files=files,
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "poses" in data
        assert "count" in data
        assert "inference_time_ms" in data
        assert "image_size" in data
        
        assert isinstance(data["poses"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["poses"])
    
    def test_detect_json_base64(self, service_url: str, sample_image_b64: str):
        """Test /v1/pose/detect with JSON base64 payload."""
        payload = {
            "image": sample_image_b64,
            "confidence_threshold": 0.5
        }
        
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            json=payload,
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "poses" in data
        assert "count" in data
        assert isinstance(data["poses"], list)
    
    def test_detect_with_data_uri(self, service_url: str, sample_image_b64: str):
        """Test detection with data URI format."""
        data_uri = f"data:image/jpeg;base64,{sample_image_b64}"
        payload = {"image": data_uri}
        
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            json=payload,
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "poses" in data
    
    def test_detect_with_custom_params(
        self, service_url: str, sample_image: bytes
    ):
        """Test detection with custom parameters."""
        files = {"image": ("test.jpg", sample_image, "image/jpeg")}
        data = {
            "confidence_threshold": "0.7",
            "iou_threshold": "0.5",
            "max_detections": "5",
            "keypoint_threshold": "0.4"
        }
        
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            files=files,
            data=data,
            timeout=10
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Max detections should be respected
        assert result["count"] <= 5


class TestPoseResponseFormat:
    """Test pose detection response format."""
    
    def test_pose_structure(self, service_url: str, sample_image: bytes):
        """Test that pose detections have correct structure."""
        files = {"image": ("test.jpg", sample_image, "image/jpeg")}
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            files=files,
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # If poses detected, validate structure
        if data["count"] > 0:
            pose = data["poses"][0]
            
            # Check required fields
            assert "person_id" in pose
            assert "bbox" in pose
            assert "bbox_confidence" in pose
            assert "keypoints" in pose
            
            # Validate bbox
            bbox = pose["bbox"]
            assert "x" in bbox
            assert "y" in bbox
            assert "width" in bbox
            assert "height" in bbox
            
            # Validate keypoints (should be 17 COCO keypoints)
            keypoints = pose["keypoints"]
            assert isinstance(keypoints, list)
            assert len(keypoints) == 17
            
            # Check first keypoint structure
            kp = keypoints[0]
            assert "name" in kp
            assert "x" in kp
            assert "y" in kp
            assert "confidence" in kp
            
            # Check skeleton connections (if enabled)
            if "skeleton" in pose:
                skeleton = pose["skeleton"]
                assert isinstance(skeleton, list)
                
                if len(skeleton) > 0:
                    conn = skeleton[0]
                    assert "from" in conn
                    assert "to" in conn
                    assert "from_index" in conn
                    assert "to_index" in conn


class TestErrorHandling:
    """Test error handling and validation."""
    
    def test_missing_image_field(self, service_url: str):
        """Test request without image field."""
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            json={"confidence_threshold": 0.5},
            timeout=5
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "message" in data["error"]
    
    def test_invalid_base64(self, service_url: str):
        """Test detection with invalid base64 data."""
        payload = {"image": "not-valid-base64!!!"}
        
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            json=payload,
            timeout=5
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
    
    def test_invalid_json(self, service_url: str):
        """Test detection with malformed JSON."""
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            data="not valid json",
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
    
    def test_empty_image(self, service_url: str):
        """Test detection with empty image data."""
        files = {"image": ("empty.jpg", b"", "image/jpeg")}
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            files=files,
            timeout=5
        )
        
        # Should handle gracefully (400 or 500)
        assert response.status_code in [400, 500]
        data = response.json()
        assert "error" in data


class TestPerformance:
    """Test performance characteristics."""
    
    def test_inference_latency(self, service_url: str, sample_image: bytes):
        """Test that inference completes within reasonable time."""
        files = {"image": ("test.jpg", sample_image, "image/jpeg")}
        
        start = time.time()
        response = requests.post(
            f"{service_url}/v1/pose/detect",
            files=files,
            timeout=10
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        
        # Should complete in < 2 seconds (generous for first request)
        assert elapsed < 2.0
        
        data = response.json()
        
        # Check reported inference time
        assert "inference_time_ms" in data
        assert data["inference_time_ms"] < 1000  # < 1 second
    
    def test_concurrent_requests(self, service_url: str, sample_image: bytes):
        """Test handling of concurrent requests."""
        import concurrent.futures
        
        files = {"image": ("test.jpg", sample_image, "image/jpeg")}
        
        def send_request():
            response = requests.post(
                f"{service_url}/v1/pose/detect",
                files=files,
                timeout=15
            )
            return response.status_code
        
        # Send 3 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(send_request) for _ in range(3)]
            results = [f.result() for f in futures]
        
        # All should succeed
        assert all(status == 200 for status in results)


class TestServiceIntegration:
    """Test integration with systemd and system resources."""
    
    def test_service_running(self):
        """Test that systemd service is active."""
        import subprocess
        
        result = subprocess.run(
            ["systemctl", "is-active", f"{SERVICE_NAME}.service"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert result.stdout.strip() == "active"
    
    def test_config_files_exist(self):
        """Test that config files are properly installed."""
        config_yaml = Path("/etc/hailo/hailo-pose.yaml")
        config_json = Path("/etc/xdg/hailo-pose/hailo-pose.json")
        
        assert config_yaml.exists()
        assert config_json.exists()
        
        # Validate JSON is readable
        with open(config_json) as f:
            config = json.load(f)
            assert "server" in config
            assert "model" in config
            assert "inference" in config
            assert "pose" in config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
