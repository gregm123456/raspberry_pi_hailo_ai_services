# Hailo Whisper Service

Speech-to-text transcription service powered by Whisper on Hailo-10H NPU for Raspberry Pi 5.

## Overview

`hailo-whisper` provides a REST API for speech-to-text transcription using Whisper models accelerated by the Hailo-10H NPU. The service exposes an OpenAI-compatible Whisper API for seamless integration with existing applications.

**Key Features:**
- OpenAI Whisper API-compatible endpoints
- Persistent model loading (low-latency repeat inference)
- Multiple audio format support (wav, mp3, ogg, flac, webm)
- Multiple output formats (json, verbose_json, text, srt, vtt)
- Voice Activity Detection (VAD) filtering
- Automatic language detection or forced language

## System Requirements

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- Python 3.10+
- Hailo driver installed (`hailo-h10-all`)
- HailoRT Python bindings
- aiohttp, PyYAML

## Installation

### Quick Start

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-whisper
sudo ./install.sh
```

### Installation with Model Warmup

Load the model immediately after installation:

```bash
sudo ./install.sh --warmup-model
```

### Verification

Verify the installation:

```bash
./verify.sh
```

Expected output:
```
[verify] ✓ Service is enabled and active
[verify] ✓ Configuration files present
[verify] ✓ Permissions configured correctly
[verify] ✓ Health endpoint responding
[verify] ✓ Models endpoint responding
```

## Configuration

Edit `/etc/hailo/hailo-whisper.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11436

model:
  name: "whisper-small"
  variant: "int8"
  keep_alive: -1  # Persistent model loading

transcription:
  language: "en"  # null for auto-detect
  temperature: 0.0
  beam_size: 5
  vad_filter: true
  max_audio_duration_seconds: 300

storage:
  cache_dir: "/var/lib/hailo-whisper/cache"

resource_limits:
  memory_max: "3G"
  cpu_quota: "80%"
```

After editing configuration:

```bash
sudo python3 /usr/lib/hailo-whisper/render_config.py \
  --input /etc/hailo/hailo-whisper.yaml \
  --output /etc/xdg/hailo-whisper/hailo-whisper.json
sudo systemctl restart hailo-whisper
```

## Usage

### Basic Transcription

```bash
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small"
```

Response:
```json
{
  "text": "Hello, this is a test transcription."
}
```

### Verbose Output with Timestamps

```bash
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small" \
  -F response_format="verbose_json"
```

Response:
```json
{
  "task": "transcribe",
  "language": "en",
  "duration": 2.5,
  "text": "Hello, this is a test transcription.",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "Hello, this is a test transcription.",
      "tokens": [1, 2, 3, 4, 5],
      "temperature": 0.0,
      "avg_logprob": -0.5,
      "compression_ratio": 1.2,
      "no_speech_prob": 0.05
    }
  ]
}
```

### SRT Subtitle Format

```bash
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small" \
  -F response_format="srt"
```

### Force Language

```bash
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small" \
  -F language="es"
```

### Python Example

```python
import requests

url = "http://localhost:11436/v1/audio/transcriptions"

with open("audio.mp3", "rb") as f:
    files = {"file": f}
    data = {
        "model": "whisper-small",
        "language": "en",
        "response_format": "verbose_json"
    }
    response = requests.post(url, files=files, data=data)
    result = response.json()
    print(result["text"])
```

## Service Management

### Start/Stop

```bash
sudo systemctl start hailo-whisper
sudo systemctl stop hailo-whisper
sudo systemctl restart hailo-whisper
```

### View Logs

```bash
sudo journalctl -u hailo-whisper -f
```

### Check Status

```bash
systemctl status hailo-whisper
```

### Health Check

```bash
curl http://localhost:11436/health
```

Response:
```json
{
  "status": "ok",
  "model": "whisper-small-int8",
  "model_loaded": true,
  "uptime_seconds": 3600,
  "transcriptions_processed": 42
}
```

## API Reference

See [API_SPEC.md](API_SPEC.md) for complete API documentation.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and resource management details.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## Uninstallation

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-whisper
sudo ./uninstall.sh
```

## License

This service follows the same licensing as the parent Hailo AI Services project.

## References

- [OpenAI Whisper](https://github.com/openai/whisper)
- [Whisper API Documentation](https://platform.openai.com/docs/api-reference/audio)
- [Hailo Developer Zone](https://hailo.ai/developer-zone/)
