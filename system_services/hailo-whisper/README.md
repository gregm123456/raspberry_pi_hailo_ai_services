# Hailo Whisper Service

Speech-to-text transcription service powered by Whisper on Hailo-10H NPU for Raspberry Pi 5.

## Overview

`hailo-whisper` provides a REST API for speech-to-text transcription using Whisper models accelerated by the Hailo-10H NPU. The service exposes an OpenAI-compatible Whisper API for seamless integration with existing applications.

Key features:
- OpenAI Whisper API-compatible endpoints
- Persistent model loading (low-latency repeat inference)
- Multiple audio format support (wav, mp3, ogg, flac, webm)
- Multiple output formats (json, verbose_json, text, srt, vtt)
- Optional VAD-style trimming
- Automatic language detection or forced language

## System Requirements

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- Python 3.10+
- Hailo driver installed (`hailo-h10-all`)
- HailoRT Python bindings
- ffmpeg (for audio decoding)

## Installation

### Quick Start

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-whisper
sudo ./install.sh
```

This will:
- Create `hailo-whisper` system user and group
- Install service to `/opt/hailo-whisper/` (venv + vendored hailo-apps)
- Install systemd unit to `/etc/systemd/system/hailo-whisper.service`
- Create config at `/etc/hailo/hailo-whisper.yaml`
- Download Whisper resources into `/var/lib/hailo-whisper/resources`
- Start and enable the service

### Installation with Model Warmup

```bash
sudo ./install.sh --warmup-model
```

### Verification

```bash
./verify.sh
```

## Configuration

Edit `/etc/hailo/hailo-whisper.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11437

model:
  name: "Whisper-Base"
  variant: "base"
  keep_alive: -1

transcription:
  language: "en"  # null for auto-detect
  temperature: 0.0
  beam_size: 5
  vad_filter: true
  max_audio_duration_seconds: 300

storage:
  cache_dir: "/var/lib/hailo-whisper/cache"
  resources_dir: "/var/lib/hailo-whisper/resources"

resource_limits:
  memory_max: "3G"
  cpu_quota: "80%"
```

After editing configuration:

```bash
sudo /opt/hailo-whisper/venv/bin/python3 /opt/hailo-whisper/render_config.py \
  --input /etc/hailo/hailo-whisper.yaml \
  --output /etc/xdg/hailo-whisper/hailo-whisper.json
sudo systemctl restart hailo-whisper
```

## Usage

All transcription requests must use `multipart/form-data` uploads following the [OpenAI Whisper API specification](https://platform.openai.com/docs/api-reference/audio/createTranscription). Raw audio payloads are not supported.

### Basic Transcription

```bash
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base"
```

Response:
```json
{
  "text": "Hello, this is a test transcription."
}
```

### Streaming from stdin (no local file required)

```bash
ffmpeg -i video.mp4 -f mp3 - | \
  curl -X POST http://localhost:11437/v1/audio/transcriptions \
    -F file="@-;filename=audio.mp3" \
    -F model="Whisper-Base"
```

### Verbose Output with Timestamps

```bash
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base" \
  -F response_format="verbose_json"
```

### SRT Subtitle Format

```bash
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base" \
  -F response_format="srt"
```

### Force Language

```bash
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base" \
  -F language="es"
```

### Python Example

```python
import requests

url = "http://localhost:11437/v1/audio/transcriptions"

# From local file
with open("audio.mp3", "rb") as f:
    files = {"file": f}
    data = {
        "model": "Whisper-Base",
        "language": "en",
        "response_format": "verbose_json"
    }
    response = requests.post(url, files=files, data=data)
    result = response.json()
    print(result["text"])

# From in-memory bytes (no file on disk)
import io
audio_bytes = get_audio_from_somewhere()  # bytes object
files = {"file": ("audio.mp3", io.BytesIO(audio_bytes), "audio/mpeg")}
data = {"model": "Whisper-Base"}
response = requests.post(url, files=files, data=data)
```

## Service Management

```bash
sudo systemctl start hailo-whisper
sudo systemctl stop hailo-whisper
sudo systemctl restart hailo-whisper
```

### View Logs

```bash
sudo journalctl -u hailo-whisper -f
```

### Health Check

```bash
curl http://localhost:11437/health
```

Response:
```json
{
  "status": "ok",
  "model": "Whisper-Base",
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
