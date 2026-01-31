import base64
import json
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np
import pytest
import requests
from PIL import Image


# Configuration
BASE_URL = os.environ.get("HAILO_SCRFD_URL", "http://localhost:5001")
TIMEOUT = 30


def create_test_image(width: int = 640, height: int = 480, format: str = "JPEG") -> str:
    """
    Create a test image with a simple pattern and encode to base64.
    
    Args:
        width: Image width
        height: Image height
        format: Image format (JPEG, PNG)
        
    Returns:
        Base64-encoded image string
    """
    # Create a simple gradient image
    img_array = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Add gradient
    for i in range(height):
        img_array[i, :, :] = [i * 255 // height, 128, 255 - i * 255 // height]
    
    # Convert to PIL Image
    img = Image.fromarray(img_array)
    
    # Encode to base64
    buffer = BytesIO()
    img.save(buffer, format=format)
    img_bytes = buffer.getvalue()
    
    return base64.b64encode(img_bytes).decode('utf-8')


def create_face_image(num_faces: int = 1) -> str:
    """
    Create a synthetic image with simple face-like patterns.
    
    Args:
        num_faces: Number of face patterns to include
        
    Returns:
        Base64-encoded image string
    """
    width, height = 640, 480
    img_array = np.ones((height, width, 3), dtype=np.uint8) * 200  # Light gray background
    
    # Draw simple face-like patterns
    face_positions = [
        (width // 4, height // 2),
        (3 * width // 4, height // 2),
        (width // 2, height // 4),
    ]
    
    for i in range(min(num_faces, len(face_positions))):
        x, y = face_positions[i]
        # Draw circle for face
        cv2.circle(img_array, (x, y), 60, (255, 200, 150), -1)
        # Draw eyes
        cv2.circle(img_array, (x - 20, y - 15), 5, (0, 0, 0), -1)
        cv2.circle(img_array, (x + 20, y - 15), 5, (0, 0, 0), -1)
        # Draw mouth
        cv2.ellipse(img_array, (x, y + 20), (20, 10), 0, 0, 180, (0, 0, 0), 2)
    
    # Convert to PIL and encode
    img = Image.fromarray(img_array)
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    img_bytes = buffer.getvalue()
    
    return base64.b64encode(img_bytes).decode('utf-8')


class TestHealthEndpoint:
    """Tests for the /health endpoint."""
    
    def test_health_check_success(self):
        """Health endpoint should return 200 and service status."""
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["service"] == "hailo-scrfd"
        assert "model_loaded" in data
        assert "model" in data
    
    def test_health_check_fields(self):
        """Health endpoint should include all required fields."""
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        data = response.json()
        
        required_fields = ["status", "service", "model_loaded", "model"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestDetectEndpoint:
    """Tests for the /v1/detect endpoint."""
    
    def test_detect_with_base64_image(self):
        """Detect faces in a base64-encoded image."""
        image_b64 = create_test_image()
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": f"data:image/jpeg;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "faces" in data
        assert "num_faces" in data
        assert "inference_time_ms" in data
        assert "model" in data
        assert isinstance(data["faces"], list)
        assert isinstance(data["num_faces"], int)
        assert data["num_faces"] == len(data["faces"])
    
    def test_detect_without_data_uri_prefix(self):
        """Detect should work with plain base64 (no data URI prefix)."""
        image_b64 = create_test_image()
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": image_b64},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "faces" in data
    
    def test_detect_with_landmarks(self):
        """Detect faces with return_landmarks=true should include landmarks."""
        image_b64 = create_face_image(num_faces=1)
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "return_landmarks": True
            },
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check if any faces detected (mock model should return at least 1)
        if data["num_faces"] > 0:
            face = data["faces"][0]
            assert "landmarks" in face
            assert len(face["landmarks"]) == 5
            
            # Check landmark structure
            landmark_types = [lm["type"] for lm in face["landmarks"]]
            expected_types = ["left_eye", "right_eye", "nose", "left_mouth", "right_mouth"]
            assert landmark_types == expected_types
            
            # Check landmark coordinates
            for lm in face["landmarks"]:
                assert "x" in lm
                assert "y" in lm
                assert isinstance(lm["x"], int)
                assert isinstance(lm["y"], int)
    
    def test_detect_without_landmarks(self):
        """Detect with return_landmarks=false should omit landmarks."""
        image_b64 = create_face_image()
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "return_landmarks": False
            },
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["num_faces"] > 0:
            face = data["faces"][0]
            assert "landmarks" not in face
    
    def test_detect_with_custom_threshold(self):
        """Detect with custom confidence threshold."""
        image_b64 = create_face_image()
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "conf_threshold": 0.3
            },
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All faces should meet threshold
        for face in data["faces"]:
            assert face["confidence"] >= 0.3
    
    def test_detect_with_annotation(self):
        """Detect with annotate=true should return annotated image."""
        image_b64 = create_face_image()
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "annotate": True
            },
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["num_faces"] > 0:
            assert "annotated_image" in data
            assert data["annotated_image"].startswith("data:image/jpeg;base64,")
    
    def test_detect_missing_image(self):
        """Detect without image should return 400."""
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"conf_threshold": 0.5},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
    
    def test_detect_invalid_json(self):
        """Detect with invalid JSON should return 400."""
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            data="not json",
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 400
    
    def test_detect_invalid_base64(self):
        """Detect with invalid base64 should return 400."""
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": "not-valid-base64!!!"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data


class TestAlignEndpoint:
    """Tests for the /v1/align endpoint."""
    
    def test_align_faces(self):
        """Align faces in an image."""
        image_b64 = create_face_image(num_faces=2)
        
        response = requests.post(
            f"{BASE_URL}/v1/align",
            json={"image": f"data:image/jpeg;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "faces" in data
        assert "num_faces" in data
        assert "model" in data
        
        # Check aligned face structure
        if data["num_faces"] > 0:
            face = data["faces"][0]
            assert "face_id" in face
            assert "bbox" in face
            assert "confidence" in face
            assert "aligned_image" in face
            assert face["aligned_image"].startswith("data:image/jpeg;base64,")
    
    def test_align_returns_multiple_faces(self):
        """Align should return all detected faces."""
        image_b64 = create_face_image(num_faces=2)
        
        response = requests.post(
            f"{BASE_URL}/v1/align",
            json={"image": f"data:image/jpeg;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Mock model should return at least 1 face
        if data["num_faces"] > 0:
            assert len(data["faces"]) == data["num_faces"]
            
            # Check face IDs are sequential
            face_ids = [f["face_id"] for f in data["faces"]]
            assert face_ids == list(range(len(face_ids)))
    
    def test_align_missing_image(self):
        """Align without image should return 400."""
        response = requests.post(
            f"{BASE_URL}/v1/align",
            json={},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data


class TestPerformance:
    """Performance and stress tests."""
    
    def test_inference_time(self):
        """Inference should complete in reasonable time."""
        image_b64 = create_test_image()
        
        start = time.time()
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": f"data:image/jpeg;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        data = response.json()
        
        # Should complete in under 5 seconds (even with model loading)
        assert elapsed < 5.0
        
        # Reported inference time should be reasonable
        assert data["inference_time_ms"] < 2000  # 2 seconds
    
    def test_concurrent_requests(self):
        """Service should handle multiple concurrent requests."""
        import concurrent.futures
        
        image_b64 = create_test_image()
        
        def send_request():
            response = requests.post(
                f"{BASE_URL}/v1/detect",
                json={"image": f"data:image/jpeg;base64,{image_b64}"},
                timeout=TIMEOUT
            )
            return response.status_code
        
        # Send 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(send_request) for _ in range(5)]
            results = [f.result() for f in futures]
        
        # All should succeed
        assert all(status == 200 for status in results)


class TestEdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_detect_very_small_image(self):
        """Detect on very small image should not crash."""
        image_b64 = create_test_image(width=32, height=32)
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": f"data:image/jpeg;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "faces" in data
    
    def test_detect_large_image(self):
        """Detect on large image should not crash."""
        image_b64 = create_test_image(width=1920, height=1080)
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": f"data:image/jpeg;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "faces" in data
    
    def test_detect_png_image(self):
        """Detect should work with PNG images."""
        image_b64 = create_test_image(format="PNG")
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={"image": f"data:image/png;base64,{image_b64}"},
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "faces" in data
    
    def test_detect_high_threshold(self):
        """Detect with very high threshold should return fewer faces."""
        image_b64 = create_face_image()
        
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "conf_threshold": 0.99
            },
            timeout=TIMEOUT
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All detected faces should meet high threshold
        for face in data["faces"]:
            assert face["confidence"] >= 0.99


class TestErrorHandling:
    """Error handling and validation."""
    
    def test_invalid_endpoint(self):
        """Invalid endpoint should return 404."""
        response = requests.get(f"{BASE_URL}/invalid", timeout=TIMEOUT)
        assert response.status_code == 404
    
    def test_wrong_http_method(self):
        """Wrong HTTP method should return 405 or similar."""
        response = requests.get(f"{BASE_URL}/v1/detect", timeout=TIMEOUT)
        assert response.status_code in [405, 400]
    
    def test_empty_post_body(self):
        """Empty POST body should return 400."""
        response = requests.post(
            f"{BASE_URL}/v1/detect",
            json=None,
            timeout=TIMEOUT
        )
        assert response.status_code == 400


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
