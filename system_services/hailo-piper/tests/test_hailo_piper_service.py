"""
Integration tests for hailo-piper TTS service.
"""

import io
import pytest
import requests
import wave


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_returns_200(self, client, service_url):
        """Health endpoint should return 200 OK."""
        response = client.get(f"{service_url}/health")
        assert response.status_code == 200
    
    def test_health_response_structure(self, client, service_url):
        """Health response should have required fields."""
        response = client.get(f"{service_url}/health")
        data = response.json()
        
        assert "status" in data
        assert "service" in data
        assert "model_loaded" in data
        assert data["service"] == "hailo-piper"
    
    def test_health_model_loaded(self, client, service_url):
        """Model should be loaded."""
        response = client.get(f"{service_url}/health")
        data = response.json()
        
        assert data["model_loaded"] is True


@pytest.mark.integration
class TestSynthesisEndpoint:
    """Test speech synthesis endpoints."""
    
    def test_synthesize_simple_text(self, client, service_url):
        """Should synthesize simple text successfully."""
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": "Hello world"},
            timeout=30
        )
        
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"
        assert len(response.content) > 0
    
    def test_synthesize_longer_text(self, client, service_url):
        """Should synthesize longer text."""
        text = "The quick brown fox jumps over the lazy dog. " * 5
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": text},
            timeout=30
        )
        
        assert response.status_code == 200
        assert len(response.content) > 1000  # Should be substantial audio
    
    def test_synthesize_with_punctuation(self, client, service_url):
        """Should handle text with punctuation."""
        text = "Hello! How are you? I'm fine, thanks. Great day, isn't it?"
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": text},
            timeout=30
        )
        
        assert response.status_code == 200
    
    def test_synthesize_empty_text_fails(self, client, service_url):
        """Should reject empty text."""
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": ""},
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
    
    def test_synthesize_missing_input_fails(self, client, service_url):
        """Should reject request without 'input' field."""
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={},
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "input" in data["error"].lower()
    
    def test_synthesize_text_too_long_fails(self, client, service_url):
        """Should reject text that's too long."""
        text = "a" * 6000  # Exceeds 5000 char limit
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": text},
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "too long" in data["error"].lower()
    
    def test_synthesize_invalid_format_fails(self, client, service_url):
        """Should reject unsupported audio format."""
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": "test", "response_format": "mp3"},
            timeout=10
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
    
    def test_synthesize_returns_valid_wav(self, client, service_url):
        """Should return valid WAV file."""
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": "Testing audio format"},
            timeout=30
        )
        
        assert response.status_code == 200
        
        # Try to parse as WAV file
        wav_buffer = io.BytesIO(response.content)
        with wave.open(wav_buffer, "rb") as wav_file:
            # Check basic WAV properties
            assert wav_file.getnchannels() in [1, 2]  # Mono or stereo
            assert wav_file.getsampwidth() == 2  # 16-bit
            assert wav_file.getframerate() > 0
            assert wav_file.getnframes() > 0


@pytest.mark.integration
class TestAlternativeSynthesisEndpoint:
    """Test alternative synthesis endpoint."""
    
    def test_synthesize_alternative_endpoint(self, client, service_url):
        """Alternative /v1/synthesize endpoint should work."""
        response = client.post(
            f"{service_url}/v1/synthesize",
            json={"text": "Testing alternative endpoint"},
            timeout=30
        )
        
        assert response.status_code == 200
        assert len(response.content) > 0
    
    def test_synthesize_alternative_missing_text(self, client, service_url):
        """Alternative endpoint should reject missing text."""
        response = client.post(
            f"{service_url}/v1/synthesize",
            json={},
            timeout=10
        )
        
        assert response.status_code == 400


@pytest.mark.integration
class TestVoicesEndpoint:
    """Test voice listing endpoint."""
    
    def test_voices_returns_200(self, client, service_url):
        """Voices endpoint should return 200 OK."""
        response = client.get(f"{service_url}/v1/voices")
        assert response.status_code == 200
    
    def test_voices_response_structure(self, client, service_url):
        """Voices response should have required structure."""
        response = client.get(f"{service_url}/v1/voices")
        data = response.json()
        
        assert "voices" in data
        assert isinstance(data["voices"], list)
        assert len(data["voices"]) > 0
    
    def test_voice_has_required_fields(self, client, service_url):
        """Each voice should have required fields."""
        response = client.get(f"{service_url}/v1/voices")
        data = response.json()
        
        voice = data["voices"][0]
        assert "id" in voice
        assert "name" in voice
        assert "language" in voice


@pytest.mark.integration
class TestConcurrentRequests:
    """Test concurrent request handling."""
    
    def test_concurrent_synthesis_requests(self, client, service_url):
        """Should handle multiple concurrent requests."""
        import concurrent.futures
        
        def synthesize(text):
            response = client.post(
                f"{service_url}/v1/audio/speech",
                json={"input": text},
                timeout=60
            )
            return response.status_code
        
        texts = [
            "Request one",
            "Request two",
            "Request three",
        ]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(synthesize, text) for text in texts]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed (though they're serialized)
        assert all(status == 200 for status in results)


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling."""
    
    def test_invalid_endpoint_returns_404(self, client, service_url):
        """Invalid endpoint should return 404."""
        response = client.get(f"{service_url}/invalid")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
    
    def test_invalid_method_returns_405(self, client, service_url):
        """Wrong HTTP method should return 405."""
        response = client.get(f"{service_url}/v1/audio/speech")
        assert response.status_code == 405
    
    def test_invalid_json_returns_400(self, client, service_url):
        """Invalid JSON should return 400."""
        response = client.post(
            f"{service_url}/v1/audio/speech",
            data="not json",
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 400


@pytest.mark.integration
class TestPerformance:
    """Test performance characteristics."""
    
    def test_synthesis_latency(self, client, service_url):
        """Synthesis should complete within reasonable time."""
        import time
        
        start = time.time()
        response = client.post(
            f"{service_url}/v1/audio/speech",
            json={"input": "Quick test"},
            timeout=30
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 5.0  # Should complete in under 5 seconds
    
    def test_health_check_fast(self, client, service_url):
        """Health check should be fast."""
        import time
        
        start = time.time()
        response = client.get(f"{service_url}/health", timeout=2)
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 1.0  # Should be nearly instant


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
