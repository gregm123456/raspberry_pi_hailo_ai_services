"""
Pytest configuration for hailo-whisper service tests.
"""

import pytest
import subprocess
import time
from pathlib import Path


@pytest.fixture(scope="session")
def hailo_whisper_url():
    """Base URL for hailo-whisper service."""
    return "http://localhost:11437"


@pytest.fixture(scope="session")
def service_running(hailo_whisper_url):
    """Ensure service is running before tests."""
    import requests
    
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{hailo_whisper_url}/health", timeout=2)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            if attempt < max_attempts - 1:
                time.sleep(1)
                continue
            else:
                pytest.skip("hailo-whisper service not running")
    
    pytest.skip("hailo-whisper service not responding")


@pytest.fixture
def test_audio_wav(tmp_path):
    """Generate a test WAV file (2 seconds of silence)."""
    audio_file = tmp_path / "test_audio.wav"
    
    # Generate test audio with ffmpeg
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-ar", "16000", "-ac", "1", "-y", str(audio_file)
    ], check=True, capture_output=True)
    
    return audio_file


@pytest.fixture
def test_audio_mp3(tmp_path):
    """Generate a test MP3 file."""
    audio_file = tmp_path / "test_audio.mp3"
    
    # Generate test audio with ffmpeg
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-ar", "16000", "-ac", "1", "-b:a", "128k", "-y", str(audio_file)
    ], check=True, capture_output=True)
    
    return audio_file
