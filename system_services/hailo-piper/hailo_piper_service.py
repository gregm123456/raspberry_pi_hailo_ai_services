#!/usr/bin/env python3
"""
Hailo Piper TTS Service - Text-to-Speech REST API.

Exposes Piper TTS as a systemd service with REST endpoints for
speech synthesis with custom voice models.
"""

import asyncio
import base64
import io
import json
import logging
import os
import signal
import sys
import threading
import traceback
import wave
from contextlib import redirect_stderr
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml
from flask import Flask, Response, jsonify, request, send_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hailo-piper-service")


class PiperServiceConfig:
    """Load and validate Piper service configuration."""
    
    def __init__(self, yaml_path: str = "/etc/hailo/hailo-piper.yaml"):
        self.yaml_path = yaml_path
        self.config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from YAML."""
        try:
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            
            logger.info(f"Loaded config from {self.yaml_path}")
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.yaml_path}, using defaults")
            self.config = self._defaults()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self._defaults()
    
    def _defaults(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "server": {"host": "0.0.0.0", "port": 5002, "debug": False},
            "piper": {
                "model_path": "/var/lib/hailo-piper/models/en_US-lessac-medium.onnx",
                "volume": 1.0,
                "length_scale": 1.0,
                "noise_scale": 0.667,
                "noise_w_scale": 0.8,
                "normalize_audio": True,
            },
            "synthesis": {
                "sample_rate": 22050,
                "format": "wav",
                "max_text_length": 5000,
            },
            "performance": {
                "worker_threads": 2,
                "request_timeout": 30,
                "cache_enabled": False,
            },
        }
    
    @property
    def server(self) -> Dict[str, Any]:
        return self.config.get("server", {})
    
    @property
    def piper(self) -> Dict[str, Any]:
        return self.config.get("piper", {})
    
    @property
    def synthesis(self) -> Dict[str, Any]:
        return self.config.get("synthesis", {})
    
    @property
    def performance(self) -> Dict[str, Any]:
        return self.config.get("performance", {})


class PiperTTS:
    """Wrapper for Piper TTS model."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.voice = None
        self.is_loaded = False
        self.lock = threading.RLock()
        
        self.model_path = config.get("model_path", "")
        self.volume = config.get("volume", 1.0)
        self.length_scale = config.get("length_scale", 1.0)
        self.noise_scale = config.get("noise_scale", 0.667)
        self.noise_w_scale = config.get("noise_w_scale", 0.8)
        self.normalize_audio = config.get("normalize_audio", True)
        
        logger.info(f"PiperTTS initialized: {self.model_path}")
    
    def load(self) -> bool:
        """Load Piper TTS model."""
        with self.lock:
            if self.is_loaded:
                return True
            
            try:
                # Check if model file exists
                if not os.path.exists(self.model_path):
                    logger.error(f"Model file not found: {self.model_path}")
                    return False
                
                json_path = self.model_path + ".json"
                if not os.path.exists(json_path):
                    logger.error(f"Model config not found: {json_path}")
                    return False
                
                # Import Piper
                try:
                    from piper import PiperVoice
                    from piper.voice import SynthesisConfig
                except ImportError:
                    logger.error("piper-tts not installed. Install with: pip3 install piper-tts")
                    return False
                
                logger.info(f"Loading Piper model: {self.model_path}")
                with redirect_stderr(StringIO()):
                    self.voice = PiperVoice.load(self.model_path)
                    self.syn_config = SynthesisConfig(
                        volume=self.volume,
                        length_scale=self.length_scale,
                        noise_scale=self.noise_scale,
                        noise_w_scale=self.noise_w_scale,
                        normalize_audio=self.normalize_audio,
                    )
                
                self.is_loaded = True
                logger.info("Piper TTS model loaded successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to load Piper model: {e}")
                traceback.print_exc()
                return False
    
    def synthesize(self, text: str, format: str = "wav") -> Optional[bytes]:
        """
        Synthesize text to speech.
        
        Args:
            text: Text to synthesize
            format: Output format (wav supported)
            
        Returns:
            Audio bytes or None on error
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return None
        
        try:
            with self.lock:
                # Synthesize to in-memory WAV buffer
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, "wb") as wav_file:
                    with redirect_stderr(StringIO()):
                        self.voice.synthesize_wav(text, wav_file, self.syn_config)
                
                wav_buffer.seek(0)
                return wav_buffer.read()
                
        except Exception as e:
            logger.error(f"Failed to synthesize text: {e}")
            traceback.print_exc()
            return None
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        if not self.is_loaded or not self.voice:
            return {}
        
        try:
            config = self.voice.config
            return {
                "model_path": self.model_path,
                "sample_rate": config.sample_rate if hasattr(config, 'sample_rate') else 22050,
                "num_speakers": config.num_speakers if hasattr(config, 'num_speakers') else 1,
                "language": config.language if hasattr(config, 'language') else "en-us",
            }
        except Exception as e:
            logger.warning(f"Could not retrieve model info: {e}")
            return {"model_path": self.model_path}


def create_app(config: PiperServiceConfig) -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Initialize Piper TTS
    piper = PiperTTS(config.piper)
    if not piper.load():
        logger.error("Failed to initialize Piper TTS model")
        sys.exit(1)
    
    max_text_length = config.synthesis.get("max_text_length", 5000)
    
    @app.route("/health", methods=["GET"])
    def health() -> Tuple[Dict[str, Any], int]:
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "hailo-piper",
            "model_loaded": piper.is_loaded,
            "model_info": piper.get_model_info(),
        }), 200
    
    @app.route("/v1/audio/speech", methods=["POST"])
    def synthesize_speech() -> Tuple[Any, int]:
        """
        Synthesize speech from text.
        
        Request body (JSON):
        {
            "input": "Text to synthesize",
            "model": "piper",
            "voice": "default",
            "response_format": "wav",
            "speed": 1.0
        }
        
        Response:
            Audio file (WAV format by default)
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            # Get text input
            text = data.get("input", "")
            if not text:
                return jsonify({"error": "Missing 'input' field"}), 400
            
            if len(text) > max_text_length:
                return jsonify({
                    "error": f"Text too long (max {max_text_length} characters)"
                }), 400
            
            # Get format (default wav)
            response_format = data.get("response_format", "wav")
            if response_format not in ["wav", "pcm"]:
                return jsonify({
                    "error": f"Unsupported format: {response_format}"
                }), 400
            
            # Synthesize audio
            import time
            start_time = time.time()
            
            audio_data = piper.synthesize(text, format=response_format)
            if audio_data is None:
                return jsonify({"error": "Synthesis failed"}), 500
            
            inference_time_ms = (time.time() - start_time) * 1000
            logger.info(f"Synthesized {len(text)} chars in {inference_time_ms:.1f}ms")
            
            # Return audio file
            return send_file(
                BytesIO(audio_data),
                mimetype="audio/wav",
                as_attachment=True,
                download_name="speech.wav"
            )
            
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/synthesize", methods=["POST"])
    def synthesize() -> Tuple[Any, int]:
        """
        Alternative synthesis endpoint with more options.
        
        Request: {"text": "...", "format": "wav"}
        Response: Audio file
        """
        try:
            data = request.get_json()
            if not data or "text" not in data:
                return jsonify({"error": "Missing 'text' field"}), 400
            
            text = data.get("text", "")
            if len(text) > max_text_length:
                return jsonify({
                    "error": f"Text too long (max {max_text_length} characters)"
                }), 400
            
            format_type = data.get("format", "wav")
            
            audio_data = piper.synthesize(text, format=format_type)
            if audio_data is None:
                return jsonify({"error": "Synthesis failed"}), 500
            
            return send_file(
                BytesIO(audio_data),
                mimetype="audio/wav",
                as_attachment=True,
                download_name="speech.wav"
            )
            
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/voices", methods=["GET"])
    def list_voices() -> Tuple[Dict[str, Any], int]:
        """
        List available voices.
        
        Response:
        {
            "voices": [
                {
                    "id": "default",
                    "name": "Lessac (Medium)",
                    "language": "en-US",
                    "gender": "neutral"
                }
            ]
        }
        """
        # For now, return the loaded model as the default voice
        model_info = piper.get_model_info()
        
        voices = [{
            "id": "default",
            "name": Path(model_info.get("model_path", "")).stem,
            "language": model_info.get("language", "en-us"),
            "gender": "neutral",
            "sample_rate": model_info.get("sample_rate", 22050),
        }]
        
        return jsonify({"voices": voices}), 200
    
    @app.errorhandler(404)
    def not_found(e) -> Tuple[Dict[str, Any], int]:
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(e) -> Tuple[Dict[str, Any], int]:
        return jsonify({"error": "Internal server error"}), 500
    
    return app


def main():
    """Main entry point."""
    logger.info("Starting Hailo Piper TTS Service")
    
    # Load configuration
    config = PiperServiceConfig()
    
    # Create Flask app
    app = create_app(config)
    
    # Get server config
    host = config.server.get("host", "0.0.0.0")
    port = config.server.get("port", 5002)
    debug = config.server.get("debug", False)
    
    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info(f"Listening on {host}:{port}")
    
    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    except Exception as e:
        logger.error(f"Service error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
