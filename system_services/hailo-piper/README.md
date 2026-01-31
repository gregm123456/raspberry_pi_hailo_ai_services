# Hailo Piper TTS Service

Deploys Piper TTS (Text-to-Speech) as a managed systemd service on Raspberry Pi 5, exposing a REST API on port 5002 for high-quality speech synthesis.

## Features

- **High-quality TTS:** Natural-sounding speech using Piper TTS models
- **REST API:** OpenAI-compatible `/v1/audio/speech` endpoint
- **Multiple voices:** Support for various Piper voice models
- **Fast synthesis:** Optimized for low-latency speech generation
- **Persistent service:** Managed by systemd with automatic restarts
- **Configurable:** YAML-based configuration for easy customization

## Prerequisites

- Raspberry Pi 5 with 64-bit Raspberry Pi OS (Trixie)
- Python 3.10+
- Python dependencies: `python3-yaml`, `python3-numpy`
- Piper TTS: Auto-installed during setup

No Hailo device required - Piper TTS runs on CPU.

## Installation

### Quick Install (with model download):

```bash
cd system_services/hailo-piper
sudo ./install.sh --download-model
```

### Manual Install:

```bash
cd system_services/hailo-piper
sudo ./install.sh
```

If installing manually, download a Piper voice model from [Piper Releases](https://github.com/rhasspy/piper/releases) and place the `.onnx` and `.onnx.json` files in `/var/lib/hailo-piper/models/`.

Recommended voices:
- `en_US-lessac-medium` (default, clear and natural)
- `en_US-amy-medium` (friendly female voice)
- `en_GB-alan-medium` (British English)

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-piper.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 5002
  debug: false

piper:
  # Path to Piper TTS ONNX model
  model_path: /var/lib/hailo-piper/models/en_US-lessac-medium.onnx
  
  # Synthesis parameters
  volume: 1.0
  length_scale: 1.0  # Speech speed (1.0 = normal)
  noise_scale: 0.667
  noise_w_scale: 0.8

synthesis:
  max_text_length: 5000  # Maximum characters per request
```

After changes, restart the service:

```bash
sudo systemctl restart hailo-piper.service
```

## Basic Usage

### Check Service Health:

```bash
curl http://localhost:5002/health
```

### Synthesize Speech (OpenAI-compatible):

```bash
curl -X POST http://localhost:5002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from Hailo Piper TTS!"}' \
  --output speech.wav

# Play the audio
aplay speech.wav
```

### Synthesize with Parameters:

```bash
curl -X POST http://localhost:5002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "input": "The quick brown fox jumps over the lazy dog.",
    "voice": "default",
    "speed": 1.0
  }' \
  --output speech.wav
```

### Alternative Synthesis Endpoint:

```bash
curl -X POST http://localhost:5002/v1/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Testing Piper TTS"}' \
  --output test.wav
```

### List Available Voices:

```bash
curl http://localhost:5002/v1/voices
```

## Service Management

```bash
# Check status
sudo systemctl status hailo-piper.service

# View logs
journalctl -u hailo-piper.service -f

# Restart service
sudo systemctl restart hailo-piper.service

# Stop service
sudo systemctl stop hailo-piper.service

# Disable service
sudo systemctl disable hailo-piper.service
```

## Verification

Run the verification script to test all functionality:

```bash
cd system_services/hailo-piper
sudo ./verify.sh
```

## Integration Examples

### Python Client:

```python
import requests

def synthesize_speech(text: str, output_file: str):
    response = requests.post(
        "http://localhost:5002/v1/audio/speech",
        json={"input": text},
        timeout=30
    )
    
    if response.status_code == 200:
        with open(output_file, "wb") as f:
            f.write(response.content)
        print(f"Speech saved to {output_file}")
    else:
        print(f"Error: {response.json()}")

synthesize_speech("Hello world!", "output.wav")
```

### Bash Script:

```bash
#!/bin/bash
TEXT="$1"
OUTPUT="${2:-speech.wav}"

curl -X POST http://localhost:5002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d "{\"input\": \"${TEXT}\"}" \
  --output "${OUTPUT}" \
  --silent --show-error --fail

if [ $? -eq 0 ]; then
    echo "Speech synthesized to ${OUTPUT}"
    aplay "${OUTPUT}"
else
    echo "Synthesis failed"
    exit 1
fi
```

## Performance

- Typical synthesis latency: 200-500ms for short phrases
- Real-time factor: ~2-5x (generates audio faster than playback)
- Memory usage: ~200-500MB (varies by model size)
- CPU usage: ~50-80% during synthesis

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## API Documentation

See [API_SPEC.md](API_SPEC.md) for complete API reference.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and system architecture.

## Uninstallation

```bash
cd system_services/hailo-piper
sudo ./uninstall.sh
```

This will remove the service, user, and optionally the configuration and downloaded models.

## Resources

- [Piper TTS GitHub](https://github.com/rhasspy/piper)
- [Piper Voice Samples](https://rhasspy.github.io/piper-samples/)
- [Download Voices](https://github.com/rhasspy/piper/releases)

## License

See parent repository for license information.
