#!/usr/bin/env python3
"""
Hailo Whisper Service - Speech-to-Text on Hailo-10H

REST API server exposing Whisper transcription accelerated by Hailo NPU.
Compatible with OpenAI Whisper API format.
"""

import asyncio
import base64
import json
import logging
import mimetypes
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import hashlib

try:
    from aiohttp import web
    import yaml
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip3 install aiohttp pyyaml")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('hailo-whisper')

# Configuration paths
XDG_CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', '/etc/xdg')
CONFIG_JSON = os.path.join(XDG_CONFIG_HOME, 'hailo-whisper', 'hailo-whisper.json')

class WhisperServiceConfig:
    """Configuration management."""
    
    def __init__(self):
        self.server_host = "0.0.0.0"
        self.server_port = 11436
        self.model_name = "whisper-small"
        self.model_variant = "int8"
        self.keep_alive = -1
        self.language = "en"
        self.temperature = 0.0
        self.beam_size = 5
        self.vad_filter = True
        self.max_audio_duration_seconds = 300  # 5 minutes
        self.cache_dir = "/var/lib/hailo-whisper/cache"
        self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON."""
        if not os.path.exists(CONFIG_JSON):
            logger.warning(f"Config not found at {CONFIG_JSON}, using defaults")
            return
        
        try:
            with open(CONFIG_JSON, 'r') as f:
                config = json.load(f)
            
            # Parse server config
            server = config.get('server', {})
            self.server_host = server.get('host', self.server_host)
            self.server_port = server.get('port', self.server_port)
            
            # Parse model config
            model = config.get('model', {})
            self.model_name = model.get('name', self.model_name)
            self.model_variant = model.get('variant', self.model_variant)
            self.keep_alive = model.get('keep_alive', self.keep_alive)
            
            # Parse transcription config
            transcription = config.get('transcription', {})
            self.language = transcription.get('language', self.language)
            self.temperature = transcription.get('temperature', self.temperature)
            self.beam_size = transcription.get('beam_size', self.beam_size)
            self.vad_filter = transcription.get('vad_filter', self.vad_filter)
            self.max_audio_duration_seconds = transcription.get('max_audio_duration_seconds', self.max_audio_duration_seconds)
            
            # Parse storage config
            storage = config.get('storage', {})
            self.cache_dir = storage.get('cache_dir', self.cache_dir)
            
            logger.info(f"Loaded config from {CONFIG_JSON}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

class WhisperService:
    """Whisper transcription service with model lifecycle management."""
    
    def __init__(self, config: WhisperServiceConfig):
        self.config = config
        self.model = None
        self.is_loaded = False
        self.load_time_ms = 0
        self.startup_time = datetime.utcnow()
        self.transcription_count = 0
    
    async def initialize(self):
        """Initialize model and prepare for inference."""
        logger.info(f"Initializing model: {self.config.model_name}-{self.config.model_variant}")
        
        try:
            # Create cache directory if it doesn't exist
            os.makedirs(self.config.cache_dir, exist_ok=True)
            
            # TODO: Implement HailoRT Whisper model loading
            # This is a placeholder for the actual Hailo Whisper integration
            # In production, this would:
            # 1. Load the Whisper HEF model via HailoRT SDK
            # 2. Initialize NPU device
            # 3. Verify device memory
            # 4. Load audio preprocessing pipeline
            
            logger.info("Model initialization placeholder (HailoRT Whisper)")
            self.is_loaded = True
            
        except Exception as e:
            logger.error(f"Model initialization failed: {e}")
            raise
    
    def _decode_audio_data(self, file_data: bytes, mime_type: str) -> Path:
        """Save uploaded audio data to temporary file."""
        
        # Determine file extension from MIME type
        ext = mimetypes.guess_extension(mime_type) or '.bin'
        if ext == '.bin':
            # Common audio formats fallback
            if 'audio/mpeg' in mime_type or 'audio/mp3' in mime_type:
                ext = '.mp3'
            elif 'audio/wav' in mime_type or 'audio/wave' in mime_type:
                ext = '.wav'
            elif 'audio/ogg' in mime_type:
                ext = '.ogg'
            elif 'audio/flac' in mime_type:
                ext = '.flac'
            elif 'audio/webm' in mime_type:
                ext = '.webm'
        
        # Create temporary file
        tmp_file = tempfile.NamedTemporaryFile(
            mode='wb',
            suffix=ext,
            dir=self.config.cache_dir,
            delete=False
        )
        tmp_file.write(file_data)
        tmp_file.close()
        
        return Path(tmp_file.name)
    
    async def transcribe_audio(
        self,
        audio_file: Path,
        language: Optional[str] = None,
        temperature: Optional[float] = None,
        prompt: Optional[str] = None,
        response_format: str = "json"
    ) -> Dict[str, Any]:
        """Transcribe audio file via Whisper."""
        
        if not self.is_loaded:
            raise RuntimeError("Model not loaded")
        
        # Use config defaults if not provided
        language = language or self.config.language
        temperature = temperature if temperature is not None else self.config.temperature
        
        try:
            # TODO: Implement actual Whisper inference
            # This is a placeholder for HailoRT Whisper inference
            # In production, this would:
            # 1. Load and decode audio file (ffmpeg/librosa)
            # 2. Preprocess audio to 16kHz mono
            # 3. Extract mel-spectrogram features
            # 4. Run encoder-decoder inference on NPU via HailoRT
            # 5. Decode output tokens to text
            # 6. Apply VAD filtering if enabled
            # 7. Format segments with timestamps
            
            # Placeholder response
            transcription_text = "[Whisper model placeholder transcription]"
            
            response = {
                "text": transcription_text,
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 2.5,
                        "text": transcription_text,
                        "tokens": [1, 2, 3, 4, 5],
                        "temperature": temperature,
                        "avg_logprob": -0.5,
                        "compression_ratio": 1.2,
                        "no_speech_prob": 0.05
                    }
                ],
                "language": language,
                "duration": 2.5,
                "inference_time_ms": 850
            }
            
            self.transcription_count += 1
            return response
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
        finally:
            # Cleanup temporary file
            if audio_file.exists():
                try:
                    audio_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {audio_file}: {e}")
    
    async def shutdown(self):
        """Unload model and clean up resources."""
        if self.model:
            logger.info("Unloading model")
            # TODO: Properly unload HailoRT model
            self.model = None
            self.is_loaded = False

class APIHandler:
    """HTTP API request handlers."""
    
    def __init__(self, service: WhisperService):
        self.service = service
    
    async def health(self, request: web.Request) -> web.Response:
        """GET /health - Service status."""
        return web.json_response({
            "status": "ok",
            "model": f"{self.service.config.model_name}-{self.service.config.model_variant}",
            "model_loaded": self.service.is_loaded,
            "uptime_seconds": (datetime.utcnow() - self.service.startup_time).total_seconds(),
            "transcriptions_processed": self.service.transcription_count
        })
    
    async def health_ready(self, request: web.Request) -> web.Response:
        """GET /health/ready - Readiness probe."""
        if self.service.is_loaded:
            return web.json_response({"ready": True})
        else:
            return web.json_response(
                {"ready": False, "reason": "model_loading"},
                status=503
            )
    
    async def list_models(self, request: web.Request) -> web.Response:
        """GET /v1/models - List available models."""
        model_id = f"{self.service.config.model_name}-{self.service.config.model_variant}"
        return web.json_response({
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": int(self.service.startup_time.timestamp()),
                    "owned_by": "hailo"
                }
            ],
            "object": "list"
        })
    
    async def transcriptions(self, request: web.Request) -> web.Response:
        """POST /v1/audio/transcriptions - Transcribe audio file."""
        
        try:
            reader = await request.multipart()
        except Exception as e:
            return web.json_response(
                {"error": {"message": f"Invalid multipart request: {e}", "type": "invalid_request_error"}},
                status=400
            )
        
        # Parse multipart form data
        audio_data = None
        audio_mime = None
        model = None
        language = None
        temperature = None
        prompt = None
        response_format = "json"
        
        async for field in reader:
            if field.name == "file":
                audio_data = await field.read()
                audio_mime = field.headers.get('Content-Type', 'application/octet-stream')
            elif field.name == "model":
                model = (await field.read()).decode('utf-8', errors='ignore')
            elif field.name == "language":
                language = (await field.read()).decode('utf-8', errors='ignore')
            elif field.name == "temperature":
                try:
                    temperature = float((await field.read()).decode('utf-8', errors='ignore'))
                except ValueError:
                    temperature = None
            elif field.name == "prompt":
                prompt = (await field.read()).decode('utf-8', errors='ignore')
            elif field.name == "response_format":
                response_format = (await field.read()).decode('utf-8', errors='ignore')
        
        # Validate required fields
        if not audio_data:
            return web.json_response(
                {"error": {"message": "Missing 'file' field", "type": "invalid_request_error"}},
                status=400
            )
        
        if not model:
            return web.json_response(
                {"error": {"message": "Missing 'model' field", "type": "invalid_request_error"}},
                status=400
            )
        
        # Check audio size
        max_size = 25 * 1024 * 1024  # 25MB
        if len(audio_data) > max_size:
            return web.json_response(
                {"error": {"message": f"Audio file too large (max {max_size} bytes)", "type": "invalid_request_error"}},
                status=400
            )
        
        # Save audio to temporary file
        try:
            audio_file = self.service._decode_audio_data(audio_data, audio_mime)
        except Exception as e:
            logger.error(f"Failed to decode audio: {e}")
            return web.json_response(
                {"error": {"message": f"Failed to process audio file: {e}", "type": "invalid_request_error"}},
                status=400
            )
        
        # Run transcription
        try:
            result = await self.service.transcribe_audio(
                audio_file=audio_file,
                language=language,
                temperature=temperature,
                prompt=prompt,
                response_format=response_format
            )
            
            # Format response based on response_format
            if response_format == "json":
                response = {
                    "text": result["text"]
                }
            elif response_format == "verbose_json":
                response = {
                    "task": "transcribe",
                    "language": result["language"],
                    "duration": result["duration"],
                    "text": result["text"],
                    "segments": result["segments"]
                }
            elif response_format == "text":
                return web.Response(text=result["text"], content_type='text/plain')
            elif response_format == "srt":
                # Format as SRT subtitles
                srt_output = self._format_srt(result["segments"])
                return web.Response(text=srt_output, content_type='text/plain')
            elif response_format == "vtt":
                # Format as WebVTT subtitles
                vtt_output = self._format_vtt(result["segments"])
                return web.Response(text=vtt_output, content_type='text/vtt')
            else:
                response = {"text": result["text"]}
            
            return web.json_response(response)
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return web.json_response(
                {"error": {"message": str(e), "type": "internal_error"}},
                status=500
            )
    
    def _format_srt(self, segments: List[Dict[str, Any]]) -> str:
        """Format segments as SRT subtitles."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = self._format_timestamp(seg["start"], srt=True)
            end = self._format_timestamp(seg["end"], srt=True)
            text = seg["text"].strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)
    
    def _format_vtt(self, segments: List[Dict[str, Any]]) -> str:
        """Format segments as WebVTT subtitles."""
        lines = ["WEBVTT\n"]
        for seg in segments:
            start = self._format_timestamp(seg["start"], srt=False)
            end = self._format_timestamp(seg["end"], srt=False)
            text = seg["text"].strip()
            lines.append(f"{start} --> {end}\n{text}\n")
        return "\n".join(lines)
    
    def _format_timestamp(self, seconds: float, srt: bool = True) -> str:
        """Format seconds as timestamp (SRT or VTT)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        if srt:
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        else:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

async def create_app(service: WhisperService) -> web.Application:
    """Create aiohttp application."""
    handler = APIHandler(service)
    app = web.Application(client_max_size=26 * 1024 * 1024)  # 26MB max request size
    
    # Routes
    app.router.add_get('/health', handler.health)
    app.router.add_get('/health/ready', handler.health_ready)
    app.router.add_get('/v1/models', handler.list_models)
    app.router.add_post('/v1/audio/transcriptions', handler.transcriptions)
    
    return app

async def main():
    """Main entry point."""
    try:
        # Load configuration
        config = WhisperServiceConfig()
        logger.info(f"Hailo Whisper Service starting")
        logger.info(f"Server: {config.server_host}:{config.server_port}")
        logger.info(f"Model: {config.model_name}-{config.model_variant}")
        
        # Initialize service
        service = WhisperService(config)
        await service.initialize()
        
        # Create and start server
        app = await create_app(service)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.server_host, config.server_port)
        await site.start()
        
        logger.info(f"Service ready at http://{config.server_host}:{config.server_port}")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
    
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await service.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
