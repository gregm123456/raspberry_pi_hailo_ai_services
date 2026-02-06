# Hailo-10H OCR Service

This service exposes a Hailo-10H accelerated OCR REST API compatible with PaddleOCR-style outputs, integrated with the device_manager for exclusive NPU access.

Quick start
- Install (run installer in this folder): `sudo bash install.sh`
- Start service: `sudo systemctl start hailo-ocr`
- Health: `curl http://localhost:11436/health`

Notes
- Server preprocessing: Images are resized with padding (letterbox) to the model input size on the server (preserves aspect ratio). Clients should send the original image (base64 or file); do not pre-resize or stretch images — the server handles aspect-ratio-preserving resizing and maps detection boxes back to original coordinates.
- Models: HEF models are downloaded to `/var/lib/hailo-ocr/resources/models/hailo10h/` during installation and loaded via device_manager.

Where to look for more
- API spec: `system_services/hailo-ocr/API_SPEC.md`
- Troubleshooting: `system_services/hailo-ocr/TROUBLESHOOTING.md`
# Hailo-10H Accelerated OCR Service

Deploys NPU-accelerated OCR (text detection and recognition) as a systemd service on Raspberry Pi 5 with Hailo-10H, integrated with device_manager for exclusive device access and model serialization.

## Features

- **NPU Accelerated:** Both detection and recognition stages run on the Hailo-10H NPU via device_manager.
- **Device Manager Integration:** Uses device_manager for exclusive NPU access, model loading, and request serialization.
- **Async Workflow:** Built on aiohttp and Hailo-10H async inference for non-blocking API performance.
- **Multi-language Support:** Separate HEF models for English and Chinese, selectable via API.
- **Isolated Deployment:** Uses a dedicated Python virtual environment and vendored hailo-apps for stability.
- **REST API:** Compatible with standard OCR conventions.

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- 64-bit Raspberry Pi OS (Trixie or Bookworm)

## Installation

```bash
cd system_services/hailo-ocr
sudo ./install.sh
```

Optional warmup (loads models into NPU memory):

```bash
sudo ./install.sh --warmup-models
```

The installer will:
1. Create a dedicated `hailo-ocr` system user and group.
2. Setup a virtual environment in `/opt/hailo-ocr/venv`.
3. Vendor `hailo-apps` for core Hailo-10H inference logic.
4. Download optimized HEF models from Hailo S3 buckets.
5. Install and enable the `hailo-ocr` systemd service.

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-ocr.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11436

ocr:
  languages: ["en"]
  det_threshold: 0.3
  rec_threshold: 0.5
  use_corrector: true

hailo_models:
  detection_hef: "ocr_det.hef"
  recognition_hefs:
    en: "ocr.hef"
    zh: "ocr_chinese.hef"
  batch_size_rec: 8  # Efficient NPU utilization
```

After changes, restart the service:
```bash
sudo systemctl restart hailo-ocr
```

## Usage

### Health Check
```bash
curl http://localhost:11436/health
```

### OCR Extraction
```bash
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,...",
    "languages": ["en"]
  }'
```

See [API_SPEC.md](API_SPEC.md) for full endpoint details.

## Verification

```bash
sudo ./verify.sh
```

## Performance

- **Throughput:** 3-5 images/second (compared to 1-2 on CPU).
- **Latency:** ~200-400ms per image (post-warmup).
- **Resource Usage:** ~2 GB RAM, ~50% CPU (post-processing/IO).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Design and resource model.
- [API_SPEC.md](API_SPEC.md) - Request/response formats.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues.

## License

This project integrates technologies including PaddleOCR (Apache 2.0) and Hailo-10H NPU infrastructure.
