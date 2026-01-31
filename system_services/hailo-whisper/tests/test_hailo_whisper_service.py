"""
Integration tests for hailo-whisper service.
"""

import pytest
import requests
import json
from pathlib import Path


class TestServiceHealth:
    """Test service health and status endpoints."""
    
    def test_health_endpoint(self, hailo_whisper_url, service_running):
        """Test GET /health returns 200 and expected fields."""
        response = requests.get(f"{hailo_whisper_url}/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "ok"
        assert "model" in data
        assert "model_loaded" in data
        assert "uptime_seconds" in data
        assert "transcriptions_processed" in data
    
    def test_health_ready_endpoint(self, hailo_whisper_url, service_running):
        """Test GET /health/ready returns readiness status."""
        response = requests.get(f"{hailo_whisper_url}/health/ready")
        assert response.status_code in [200, 503]
        
        data = response.json()
        assert "ready" in data
        
        if response.status_code == 200:
            assert data["ready"] is True
        else:
            assert data["ready"] is False
            assert "reason" in data


class TestModelsEndpoint:
    """Test model listing endpoint."""
    
    def test_list_models(self, hailo_whisper_url, service_running):
        """Test GET /v1/models returns available models."""
        response = requests.get(f"{hailo_whisper_url}/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) > 0
        
        # Check first model structure
        model = data["data"][0]
        assert "id" in model
        assert "object" in model
        assert model["object"] == "model"
        assert "created" in model
        assert "owned_by" in model


class TestTranscriptionEndpoint:
    """Test audio transcription endpoint."""
    
    def test_transcription_wav_json(self, hailo_whisper_url, service_running, test_audio_wav):
        """Test transcription with WAV file and JSON response."""
        with open(test_audio_wav, "rb") as f:
            files = {"file": f}
            data = {"model": "whisper-small"}
            
            response = requests.post(
                f"{hailo_whisper_url}/v1/audio/transcriptions",
                files=files,
                data=data
            )
        
        assert response.status_code == 200
        result = response.json()
        assert "text" in result
        assert isinstance(result["text"], str)
    
    def test_transcription_mp3_verbose_json(self, hailo_whisper_url, service_running, test_audio_mp3):
        """Test transcription with MP3 file and verbose JSON response."""
        with open(test_audio_mp3, "rb") as f:
            files = {"file": f}
            data = {
                "model": "whisper-small",
                "response_format": "verbose_json"
            }
            
            response = requests.post(
                f"{hailo_whisper_url}/v1/audio/transcriptions",
                files=files,
                data=data
            )
        
        assert response.status_code == 200
        result = response.json()
        
        # Check verbose_json structure
        assert "text" in result
        assert "task" in result
        assert "language" in result
        assert "duration" in result
        assert "segments" in result
        assert isinstance(result["segments"], list)
    
    def test_transcription_text_format(self, hailo_whisper_url, service_running, test_audio_wav):
        """Test transcription with text response format."""
        with open(test_audio_wav, "rb") as f:
            files = {"file": f}
            data = {
                "model": "whisper-small",
                "response_format": "text"
            }
            
            response = requests.post(
                f"{hailo_whisper_url}/v1/audio/transcriptions",
                files=files,
                data=data
            )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain"
        assert isinstance(response.text, str)
    
    def test_transcription_srt_format(self, hailo_whisper_url, service_running, test_audio_wav):
        """Test transcription with SRT subtitle format."""
        with open(test_audio_wav, "rb") as f:
            files = {"file": f}
            data = {
                "model": "whisper-small",
                "response_format": "srt"
            }
            
            response = requests.post(
                f"{hailo_whisper_url}/v1/audio/transcriptions",
                files=files,
                data=data
            )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain"
        
        # Check SRT format structure (basic validation)
        text = response.text
        assert "-->" in text  # Timestamp separator
    
    def test_transcription_with_language(self, hailo_whisper_url, service_running, test_audio_wav):
        """Test transcription with explicit language parameter."""
        with open(test_audio_wav, "rb") as f:
            files = {"file": f}
            data = {
                "model": "whisper-small",
                "language": "en"
            }
            
            response = requests.post(
                f"{hailo_whisper_url}/v1/audio/transcriptions",
                files=files,
                data=data
            )
        
        assert response.status_code == 200
        result = response.json()
        assert "text" in result
    
    def test_transcription_missing_file(self, hailo_whisper_url, service_running):
        """Test transcription without file field returns 400."""
        data = {"model": "whisper-small"}
        response = requests.post(
            f"{hailo_whisper_url}/v1/audio/transcriptions",
            data=data
        )
        
        assert response.status_code == 400
        result = response.json()
        assert "error" in result
        assert "message" in result["error"]
    
    def test_transcription_missing_model(self, hailo_whisper_url, service_running, test_audio_wav):
        """Test transcription without model field returns 400."""
        with open(test_audio_wav, "rb") as f:
            files = {"file": f}
            
            response = requests.post(
                f"{hailo_whisper_url}/v1/audio/transcriptions",
                files=files
            )
        
        assert response.status_code == 400
        result = response.json()
        assert "error" in result
        assert "message" in result["error"]


class TestErrorHandling:
    """Test error handling and validation."""
    
    def test_invalid_endpoint(self, hailo_whisper_url, service_running):
        """Test requesting non-existent endpoint returns 404."""
        response = requests.get(f"{hailo_whisper_url}/invalid/endpoint")
        assert response.status_code == 404
    
    def test_transcription_invalid_json_body(self, hailo_whisper_url, service_running):
        """Test transcription with invalid JSON returns error."""
        response = requests.post(
            f"{hailo_whisper_url}/v1/audio/transcriptions",
            data="not-valid-multipart",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code in [400, 415]


class TestConcurrentRequests:
    """Test concurrent request handling."""
    
    def test_multiple_transcriptions(self, hailo_whisper_url, service_running, test_audio_wav):
        """Test multiple sequential transcriptions."""
        for i in range(3):
            with open(test_audio_wav, "rb") as f:
                files = {"file": f}
                data = {"model": "whisper-small"}
                
                response = requests.post(
                    f"{hailo_whisper_url}/v1/audio/transcriptions",
                    files=files,
                    data=data
                )
                
                assert response.status_code == 200
                result = response.json()
                assert "text" in result


@pytest.mark.skipif(
    not Path("/etc/hailo/hailo-whisper.yaml").exists(),
    reason="Service not installed"
)
class TestConfiguration:
    """Test configuration loading."""
    
    def test_config_file_exists(self):
        """Test configuration file exists."""
        assert Path("/etc/hailo/hailo-whisper.yaml").exists()
    
    def test_json_config_exists(self):
        """Test rendered JSON config exists."""
        assert Path("/etc/xdg/hailo-whisper/hailo-whisper.json").exists()
    
    def test_json_config_valid(self):
        """Test JSON config is valid."""
        config_path = Path("/etc/xdg/hailo-whisper/hailo-whisper.json")
        with open(config_path) as f:
            config = json.load(f)
        
        assert "server" in config
        assert "model" in config
        assert "transcription" in config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
