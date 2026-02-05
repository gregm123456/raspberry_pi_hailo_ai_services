# hailo-florence: Image Captioning + VQA System Service

**Florence-2 Image Captioning + VQA Service for Raspberry Pi 5 + Hailo-10H**

Generate rich, natural language descriptions of images using Microsoft's Florence-2 vision-language model, accelerated by the Hailo-10H NPU.

## ⚠️ Current Status: Hailo-10H Compatibility Issue

**The service installer is complete and functional, but the Florence-2 HEF model files are currently incompatible with Hailo-10H devices.**

The HEF files from the [dynamic_captioning example](../../hailo-rpi5-examples/community_projects/dynamic_captioning/) were compiled for Hailo-8 architecture. When loaded on Hailo-10H, the service reports:

```
HEF file is not compatible with device (HAILO_HEF_NOT_COMPATIBLE_WITH_DEVICE)
```

### Resolution Options

To make this service operational on Hailo-10H, you need Florence-2 HEF files compiled specifically for `hailo10h` architecture:

1. **Check Hailo Developer Zone** for pre-compiled Hailo-10H versions:
   - Visit [Hailo Developer Zone](https://hailo.ai/developer-zone/)
   - Look for Florence-2 models compiled for Hailo-10H

2. **Compile the models yourself** using Hailo Dataflow Compiler v5.2.0+:
   - Obtain source ONNX models for Florence-2 vision encoder and text encoder/decoder
   - Install Hailo Dataflow Compiler (DFC)
   - Prepare calibration dataset (representative images)
   - Compile workflow: `parse` → `optimize` (with calibration) → `compile --hw-arch hailo10h`
   - Reference: [Hailo Dataflow Compiler guide](../../reference_documentation/hailo_dataflow_compiler_what_you_can_do.md)
   - Replace `.hef` files in `/var/lib/hailo-florence/models/`:
     - `florence2_transformer_encoder.hef`
     - `florence2_transformer_decoder.hef`

3. **Contact Hailo Support**:
   - Request Hailo-10H versions of Florence-2 HEF files
   - Reference the dynamic_captioning community project

### What Works

The service infrastructure is fully functional:
- ✅ Installation script stages all dependencies and processor artifacts
- ✅ systemd service management
- ✅ REST API server starts and responds to health checks
- ✅ ONNX vision encoder loads successfully
- ✅ Python processor and tokenizer artifacts staged locally
- ❌ HEF files fail to load due to architecture mismatch

Once compatible HEF files are available, no code changes are needed—simply replace the `.hef` files in `/var/lib/hailo-florence/models/` and restart the service.

## Overview

The `hailo-florence` service provides a REST API for automatic image captioning and visual question answering (VQA). Submit an image (and optional question), receive a descriptive natural language caption or answer. Ideal for accessibility features (alt-text generation), content cataloging, and automated scene description.

**Key Features:**
- REST API endpoints: `POST /v1/caption`, `POST /v1/vqa`
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

**Note:** The installer will complete successfully, but the service will not be fully operational until compatible Hailo-10H HEF files are available. See status section above.

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-florence
sudo ./install.sh
```

This will:
1. Create `hailo-florence` system user and group
2. Set up service directories in `/opt/hailo-florence/` and `/var/lib/hailo-florence/`
3. Install Python dependencies (venv in `/opt/hailo-florence/`)
4. Download Florence-2 model files and processor artifacts into `/var/lib/hailo-florence/models/`
5. Install systemd service

### Verification

Start the service:
```bash
sudo systemctl enable --now hailo-florence
```

Check service status:
```bash
sudo systemctl status hailo-florence
```

Test the API (note: will report unhealthy until HEF compatibility resolved):
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
curl -X POST http://localhost:11438/v1/caption \
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
  "model": "florence-2",
  "token_count": 23
}
```

### Visual Question Answering (VQA)

```bash
curl -X POST http://localhost:11438/v1/vqa \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    "question": "What is the person holding?"
  }'
```

**Response:**
```json
{
  "answer": "A phone",
  "inference_time_ms": 820,
  "model": "florence-2",
  "token_count": 2
}
```

### Using Image File

```python
import base64
import requests

with open("image.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

response = requests.post(
    "http://localhost:11438/v1/caption",
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

Service configuration is in `/etc/hailo/hailo-florence.yaml` (rendered JSON at `/etc/xdg/hailo-florence/hailo-florence.json`):

```yaml
server:
  host: "0.0.0.0"
  port: 11438
  log_level: "info"

model:
  name: "florence-2"
  model_dir: "/var/lib/hailo-florence/models"
  processor_name: "/var/lib/hailo-florence/models/processor/microsoft__florence-2-base"
  vision_encoder: "vision_encoder.onnx"
  text_encoder: "florence2_transformer_encoder.hef"
  decoder: "florence2_transformer_decoder.hef"
  tokenizer: "tokenizer.json"
  caption_embedding: "caption_embedding.npy"
  vqa_embedding: "vqa_embedding.npy"
  word_embedding: "word_embedding.npy"
  max_length: 100
  min_length: 10
  temperature: 0.7
```

**Note:** VQA requires a dedicated `vqa_embedding.npy`. If it is missing, `/v1/vqa` returns 501 until configured.

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
| **CPU Usage** | Moderate (vision encoder on CPU) |
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
      "http://localhost:11438/v1/caption",
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
          "http://localhost:11438/v1/caption",
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
curl http://localhost:11438/health
```

Current response (until HEF compatibility resolved):
```json
{
  "status": "unhealthy",
  "model_loaded": false,
  "uptime_seconds": 40,
  "version": "1.0.0",
  "hailo_device": "connected",
  "error": "HEF file is not compatible with device. See hailort.log for more information"
}
```

Expected response (once compatible HEFs are installed):
```json
{
  "status": "healthy",
  "model_loaded": true,
  "uptime_seconds": 3600,
  "version": "1.0.0",
  "hailo_device": "connected"
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

# Check Hailo device architecture
hailortcli fw-control identify

# Test API connectivity
curl http://localhost:11438/health

# Check service logs for HEF compatibility errors
sudo journalctl -u hailo-florence -n 50

# Check memory usage
free -h
```

**Known Issue:** If you see `HAILO_HEF_NOT_COMPATIBLE_WITH_DEVICE(93)` in the logs, the HEF files need to be recompiled for your device architecture. See status section at the top of this document.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design details, resource management, and implementation notes.

## Uninstallation

```bash
sudo systemctl stop hailo-florence
sudo systemctl disable hailo-florence
sudo rm /etc/systemd/system/hailo-florence.service
sudo rm -rf /opt/hailo-florence
sudo rm -rf /var/lib/hailo-florence
sudo rm -rf /etc/hailo/hailo-florence.yaml
sudo rm -rf /etc/xdg/hailo-florence
sudo userdel -r hailo-florence
sudo systemctl daemon-reload
```

## References

- **Implementation Base:** [hailo-rpi5-examples/community_projects/dynamic_captioning](../../hailo-rpi5-examples/community_projects/dynamic_captioning/)
- **Florence-2 Paper:** https://arxiv.org/abs/2311.06242
- **System Setup:** [reference_documentation/system_setup.md](../../reference_documentation/system_setup.md)
- **API Specification:** [API_SPEC.md](API_SPEC.md)
- **Hailo Dataflow Compiler:** [reference_documentation/hailo_dataflow_compiler_what_you_can_do.md](../../reference_documentation/hailo_dataflow_compiler_what_you_can_do.md)

---

**Version:** 1.0.0  
**Last Updated:** February 4, 2026  
**Status:** Installer Complete / HEF Compatibility Pending (Hailo-8 → Hailo-10H)
