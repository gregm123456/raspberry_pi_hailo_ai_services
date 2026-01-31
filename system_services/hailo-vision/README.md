# Hailo Vision Service

Deploys Qwen VLM (Qwen2-VL-2B-Instruct) as a systemd service on Raspberry Pi 5 with Hailo-10H, exposing a chat-based vision API on port 11435 with OpenAI-compatible endpoints.

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- Python YAML support: `sudo apt install python3-yaml`
- HailoRT SDK with VLM bindings (5.2.0+)

The installer will check for HailoRT VLM library availability and provide installation guidance if missing.

## Installation

```bash
cd system_services/hailo-vision
sudo ./install.sh
```

Optional warmup (pulls vision model):

```bash
sudo ./install.sh --warmup-model
```

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-vision.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11435

model:
  name: "qwen2-vl-2b-instruct"
  # keep_alive: -1  # -1 = persistent, 0 = unload after request, N = unload after N seconds (default 300)

generation:
  temperature: 0.7
  max_tokens: 200
  top_p: 0.9
```

After changes, re-run:

```bash
sudo ./install.sh
```

## Basic Usage

Query service status:

```bash
curl http://localhost:11435/health
```

### Vision Inference

**Chat-based image analysis (OpenAI-compatible):**

```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image",
            "image_url": "data:image/jpeg;base64,/9j/4AAQ..."
          },
          {
            "type": "text",
            "text": "Describe what you see in this image."
          }
        ]
      }
    ],
    "temperature": 0.7,
    "max_tokens": 200,
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1706745600,
  "model": "qwen2-vl-2b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "In this image, I can see a person wearing a red shirt standing in front of a brick wall. The person appears to be looking down at their phone..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 256,
    "completion_tokens": 42,
    "total_tokens": 298
  }
}
```

Check service status:

```bash
sudo systemctl status hailo-vision.service
sudo journalctl -u hailo-vision.service -f
```

## Verification

```bash
sudo ./verify.sh
```

## Uninstall

```bash
sudo ./uninstall.sh
```

Optional cleanup:

```bash
sudo ./uninstall.sh --remove-user --purge-data
```

## Documentation

- API reference: [API_SPEC.md](API_SPEC.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## Concurrent Deployment

This service is designed to run alongside `hailo-ollama` and other AI services. Memory budgets:
- **Vision (Qwen2-VL-2B):** ~2-4 GB
- **LLM (Qwen2 1.5B):** ~2-4 GB
- **Total:** ~4-8 GB (within Pi 5 constraints)

Monitor concurrent service performance via:

```bash
ps aux | grep hailo
free -h
vcgencmd measure_temp  # Thermal status
```
