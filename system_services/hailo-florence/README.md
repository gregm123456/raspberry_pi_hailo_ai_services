# hailo-florence: Image Captioning System Service

**Florence-2 Image Captioning Service for Raspberry Pi 5 + Hailo-10H**

Generate rich, natural language descriptions of images using Microsoft's Florence-2 vision-language model, accelerated by the Hailo-10H NPU.

## Overview

The `hailo-florence` service provides a REST API for automatic image captioning. Submit an image, receive a descriptive natural language caption. Ideal for accessibility features (alt-text generation), content cataloging, and automated scene description.

**Key Features:**
- REST API endpoint: `POST /v1/caption`
- Rich narrative descriptions of visual content
- Arbitrary vocabulary (not limited to predefined classes)
- Base64 or file-based image input
- Scene description with spatial relationships and context
- systemd-managed persistent service

## Quick Start

### Prerequisites

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- Hailo driver installed (see [system setup](../../reference_documentation/system_setup.md))
- Python 3.10+

### Installation

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-florence
sudo ./install.sh
```

This will:
1. Create `hailo-florence` system user and group
2. Set up service directories in `/opt/hailo/florence/`
3. Install Python dependencies
4. Download Florence-2 model files
5. Install and enable systemd service
6. Start the service

### Verification

Check service status:
```bash
sudo systemctl status hailo-florence
```

Test the API:
```bash
./verify.sh
```

View logs:
```bash
sudo journalctl -u hailo-florence -f
```

## API Usage

### Basic Caption Generation

```bash
curl -X POST http://localhost:8082/v1/caption \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    "max_length": 100
  }'
```

**Response:**
```json
{
  "caption": "A person wearing a red shirt and blue jeans standing in front of a brick building while looking at their phone",
  "inference_time_ms": 750,
  "model": "florence-2"
}
```

### Using Image File

```python
import base64
import requests

with open("image.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

response = requests.post(
    "http://localhost:8082/v1/caption",
    json={
        "image": f"data:image/jpeg;base64,{image_b64}",
        "max_length": 150,
        "min_length": 20
    }
)

print(response.json()["caption"])
```

See [API_SPEC.md](API_SPEC.md) for complete API documentation.

## Configuration

Service configuration is in `/etc/hailo/florence/config.yaml`:

```yaml
service:
  host: "0.0.0.0"
  port: 8082
  workers: 1

model:
  name: "florence-2"
  max_length: 100
  min_length: 10
  temperature: 0.7

resources:
  memory_limit: "4G"
  vram_budget: "3G"

logging:
  level: "INFO"
  format: "json"
```

After editing config, restart the service:
```bash
sudo systemctl restart hailo-florence
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | ~1-2 fps |
| **Latency** | 500-1000ms per image |
| **VRAM Usage** | 2-3 GB |
| **CPU Usage** | Moderate (encoder on CPU) |
| **Thermal Impact** | Moderate-High |

**Note:** Florence-2 is more resource-intensive than CLIP but provides richer descriptive output. Suitable for batch processing and accessibility use cases rather than real-time applications.

## Use Cases

### 1. Accessibility Alt-Text Generation
Generate automatic image descriptions for screen readers:
```python
def generate_alt_text(image_path):
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    response = requests.post(
        "http://localhost:8082/v1/caption",
        json={"image": f"data:image/jpeg;base64,{image_b64}"}
    )
    return response.json()["caption"]
```

### 2. Video Scene Annotation
Process video frames to generate metadata:
```python
import cv2

cap = cv2.VideoCapture("video.mp4")
captions = []

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Process every 30th frame
    if cap.get(cv2.CAP_PROP_POS_FRAMES) % 30 == 0:
        _, buffer = cv2.imencode('.jpg', frame)
        image_b64 = base64.b64encode(buffer).decode('utf-8')
        
        response = requests.post(
            "http://localhost:8082/v1/caption",
            json={"image": f"data:image/jpeg;base64,{image_b64}"}
        )
        captions.append({
            "timestamp": cap.get(cv2.CAP_PROP_POS_MSEC),
            "caption": response.json()["caption"]
        })
```

### 3. Photo Library Cataloging
Generate searchable text descriptions for image archives:
```python
from pathlib import Path

image_dir = Path("photos/")
for image_path in image_dir.glob("*.jpg"):
    caption = generate_alt_text(image_path)
    
    # Save caption as sidecar file
    caption_path = image_path.with_suffix(".txt")
    caption_path.write_text(caption)
```

## Service Management

### Start/Stop/Restart
```bash
sudo systemctl start hailo-florence
sudo systemctl stop hailo-florence
sudo systemctl restart hailo-florence
```

### Enable/Disable Auto-Start
```bash
sudo systemctl enable hailo-florence   # Start on boot
sudo systemctl disable hailo-florence  # Don't start on boot
```

### View Logs
```bash
# Follow live logs
sudo journalctl -u hailo-florence -f

# Show last 100 lines
sudo journalctl -u hailo-florence -n 100

# Show logs since boot
sudo journalctl -u hailo-florence -b
```

### Health Check
```bash
curl http://localhost:8082/health
```

Expected response:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "uptime_seconds": 3600,
  "version": "1.0.0"
}
```

## Concurrent Operation

Florence-2 can run alongside other AI services:

| Service | VRAM | CPU | Compatible |
|---------|------|-----|------------|
| hailo-ollama | 2-4 GB | Moderate | ✅ Yes (resource managed) |
| hailo-clip | 1-2 GB | Low | ✅ Yes |
| hailo-vision (Qwen VLM) | 2-4 GB | Moderate | ⚠️ Tight (6-7 GB total) |

**Recommendation:** Run Florence-2 with either hailo-ollama OR hailo-vision, not both simultaneously, to avoid memory pressure.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

**Quick Diagnostics:**
```bash
# Check if service is running
systemctl is-active hailo-florence

# Check Hailo device
hailortcli fw-control identify

# Test API connectivity
curl http://localhost:8082/health

# Check memory usage
free -h
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design details, resource management, and implementation notes.

## Uninstallation

```bash
sudo systemctl stop hailo-florence
sudo systemctl disable hailo-florence
sudo rm /etc/systemd/system/hailo-florence.service
sudo rm -rf /opt/hailo/florence
sudo rm -rf /etc/hailo/florence
sudo userdel -r hailo-florence
sudo systemctl daemon-reload
```

## References

- **Implementation Base:** [hailo-rpi5-examples/community_projects/dynamic_captioning](../../hailo-rpi5-examples/community_projects/dynamic_captioning/)
- **Florence-2 Paper:** https://arxiv.org/abs/2311.06242
- **System Setup:** [reference_documentation/system_setup.md](../../reference_documentation/system_setup.md)
- **API Specification:** [API_SPEC.md](API_SPEC.md)

---

**Version:** 1.0.0  
**Last Updated:** January 31, 2026  
**Status:** Stable
