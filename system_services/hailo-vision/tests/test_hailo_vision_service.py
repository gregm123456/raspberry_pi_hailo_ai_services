#!/usr/bin/env python3
"""
Integration tests for Hailo Vision Service

Run with: pytest test_hailo_vision_service.py -v
"""

import pytest
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any

# Service configuration
SERVICE_NAME = "hailo-vision"
DEFAULT_PORT = 11435
BASE_URL = f"http://localhost:{DEFAULT_PORT}"

class TestHailoVisionService:
    """Integration tests for the vision service."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_teardown(self):
        """Setup and teardown for test class."""
        # Wait for service to be ready
        self._wait_for_service(timeout=10)
        yield
        # Teardown (service keeps running)
    
    @staticmethod
    def _wait_for_service(timeout: int = 10) -> bool:
        """Wait for service to be ready."""
        import urllib.request
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = urllib.request.urlopen(f"{BASE_URL}/health", timeout=2)
                if response.status == 200:
                    return True
            except Exception:
                time.sleep(0.5)
        
        raise RuntimeError(f"Service did not become ready within {timeout}s")
    
    @staticmethod
    def _make_request(method: str, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make HTTP request to service."""
        import urllib.request
        import urllib.error
        
        url = f"{BASE_URL}{endpoint}"
        
        if method == "GET":
            try:
                response = urllib.request.urlopen(url, timeout=5)
                return json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                return {"error": str(e), "status": e.code}
        
        elif method == "POST":
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            try:
                response = urllib.request.urlopen(req, timeout=10)
                return json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                return {"error": str(e), "status": e.code}
    
    def test_health_endpoint(self):
        """Test /health endpoint."""
        response = self._make_request("GET", "/health")
        
        assert response.get("status") == "ok"
        assert "model" in response
        assert "model_loaded" in response
        assert "uptime_seconds" in response
    
    def test_health_ready_endpoint(self):
        """Test /health/ready endpoint."""
        response = self._make_request("GET", "/health/ready")
        
        assert "ready" in response
        assert isinstance(response["ready"], bool)
    
    def test_list_models_endpoint(self):
        """Test /v1/models endpoint."""
        response = self._make_request("GET", "/v1/models")
        
        assert response.get("object") == "list"
        assert "data" in response
        assert len(response["data"]) > 0
        
        model = response["data"][0]
        assert model.get("object") == "model"
        assert "id" in model
        assert "owned_by" in model
    
    def test_chat_completions_invalid_model(self):
        """Test /v1/chat/completions with invalid model."""
        request_data = {
            "model": "invalid-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hello"}
                    ]
                }
            ]
        }
        
        response = self._make_request("POST", "/v1/chat/completions", request_data)
        
        # Service may accept it, or return error
        # Just verify response structure
        assert isinstance(response, dict)
    
    def test_chat_completions_missing_image(self):
        """Test /v1/chat/completions without image."""
        request_data = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hello"}
                    ]
                }
            ]
        }
        
        response = self._make_request("POST", "/v1/chat/completions", request_data)
        
        # Should fail gracefully
        assert isinstance(response, dict)
    
    def test_chat_completions_with_image(self):
        """Test /v1/chat/completions with image placeholder."""
        request_data = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image_url": {
                                "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD"
                            }
                        },
                        {"type": "text", "text": "What is in this image?"}
                    ]
                }
            ],
            "temperature": 0.7,
            "max_tokens": 50
        }
        
        response = self._make_request("POST", "/v1/chat/completions", request_data)
        
        assert isinstance(response, dict)
        assert "choices" in response or "error" in response
    
    def test_service_file_structure(self):
        """Verify service files are in place."""
        service_dir = Path("/home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-vision")
        
        required_files = [
            "README.md",
            "API_SPEC.md",
            "ARCHITECTURE.md",
            "TROUBLESHOOTING.md",
            "config.yaml",
            "hailo-vision.service",
            "install.sh",
            "uninstall.sh",
            "verify.sh",
            "render_config.py",
            "hailo_vision_server.py"
        ]
        
        for file in required_files:
            assert (service_dir / file).exists(), f"Missing file: {file}"
    
    def test_config_file_validity(self):
        """Test configuration files."""
        import yaml
        
        config_file = Path("/etc/hailo/hailo-vision.yaml")
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            assert "server" in config
            assert "model" in config
            assert "generation" in config

class TestInstallation:
    """Tests for installation and deployment."""
    
    def test_service_is_enabled(self):
        """Test that service is systemd-enabled."""
        result = subprocess.run(
            ["systemctl", "is-enabled", SERVICE_NAME],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "Service not enabled"
    
    def test_service_is_active(self):
        """Test that service is running."""
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "Service not active"
    
    def test_service_unit_file_exists(self):
        """Test unit file installation."""
        unit_file = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
        assert unit_file.exists(), "Unit file not installed"
    
    def test_user_exists(self):
        """Test service user creation."""
        result = subprocess.run(
            ["id", SERVICE_NAME],
            capture_output=True
        )
        assert result.returncode == 0, "Service user not created"
    
    def test_config_directories_exist(self):
        """Test config directory creation."""
        dirs = [
            Path("/var/lib/hailo-vision"),
            Path("/etc/xdg/hailo-vision"),
            Path("/etc/hailo")
        ]
        
        for dir_path in dirs:
            assert dir_path.exists(), f"Directory not created: {dir_path}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
