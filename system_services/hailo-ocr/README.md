# Hailo OCR Service

Deploys PaddleOCR (text detection and recognition) as a systemd service on Raspberry Pi 5 with Hailo-10H, exposing a REST API on port 11436 for document scanning, text extraction, and OCR analysis.

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- Python dependencies: `sudo apt install python3-yaml python3-pillow`
- PaddleOCR models (downloaded on first run or during warmup)

The installer will check for required Python packages and provide installation guidance if missing.

## Installation

```bash
cd system_services/hailo-ocr
sudo ./install.sh
```

Optional warmup (downloads OCR models):

```bash
sudo ./install.sh --warmup-models
```

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-ocr.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11436

ocr:
  # Model languages: 'en' for English, 'ch_sim' for Simplified Chinese, etc.
  languages:
    - en
  # Detection model: use_gpu=false for Hailo acceleration (CPU fallback)
  use_gpu: false
  # Enable text recognition
  enable_recognition: true
  # Confidence thresholds
  det_threshold: 0.3
  rec_threshold: 0.5

processing:
  # Max image size for processing (0 = no limit)
  max_image_size: 4096
  # JPEG quality for internal processing
  jpeg_quality: 90
  # Enable caching of OCR results
  enable_caching: true
  cache_ttl_seconds: 3600
```

After changes, restart the service:

```bash
sudo systemctl restart hailo-ocr
```

## Basic Usage

Query service status:

```bash
curl http://localhost:11436/health
```

### Text Detection and Recognition

**Extract text from image:**

```bash
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,/9j/4AAQ...",
    "languages": ["en"],
    "enable_recognition": true
  }'
```

**Response:**
```json
{
  "success": true,
  "text": "Sample text extracted from image",
  "regions": [
    {
      "bbox": [[10, 20], [100, 20], [100, 50], [10, 50]],
      "text": "Sample",
      "confidence": 0.95,
      "type": "text"
    }
  ],
  "processing_time_ms": 450,
  "model_version": "paddleocr-2.7.0"
}
```

**Batch OCR (multiple images):**

```bash
curl -X POST http://localhost:11436/v1/ocr/batch \
  -H "Content-Type: application/json" \
  -d '{
    "images": [
      "data:image/jpeg;base64,/9j/4AAQ...",
      "data:image/png;base64,iVBORw0KG..."
    ],
    "languages": ["en"]
  }'
```

Check service status:

```bash
sudo systemctl status hailo-ocr.service
sudo journalctl -u hailo-ocr.service -f
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

This service is designed to run alongside `hailo-ollama`, `hailo-vision`, and other AI services. Memory budgets:
- **OCR (PaddleOCR):** ~1-2 GB
- **LLM (Qwen2 1.5B):** ~2-4 GB
- **Vision (Qwen2-VL-2B):** ~2-4 GB
- **Total:** ~5-10 GB (monitor on Pi 5)

Monitor concurrent service performance via:

```bash
ps aux | grep hailo
free -h
vcgencmd measure_temp  # Thermal status
```

## Performance Notes

- **First request:** ~2-3 seconds (model initialization)
- **Subsequent requests:** ~200-800 ms per image (resolution dependent)
- **Typical memory:** 1.5-2 GB with models loaded
- **Batch processing:** Scales linearly with image count

## License

PaddleOCR is distributed under the Apache 2.0 License. See [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) for details.
