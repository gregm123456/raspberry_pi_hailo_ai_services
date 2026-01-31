# Hailo CLIP Service

Deploys CLIP zero-shot image classification as a managed systemd service on Raspberry Pi 5 with Hailo-10H, exposing a REST API on port 5000.

## Features

- **Zero-shot classification:** Classify images using arbitrary text prompts without retraining
- **Runtime-configurable prompts:** Change classification categories on-the-fly
- **Hailo-accelerated:** Optimized for Hailo-10H NPU with low latency (33-50ms)
- **RESTful API:** OpenAI Vision API-compatible design
- **Concurrent requests:** Thread-safe multi-worker support
- **Embeddings export:** Get raw CLIP embeddings for custom applications

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- Python YAML support: `sudo apt install python3-yaml`
- Python image libraries: `sudo apt install python3-pil python3-opencv`

The installer will check for the hailo-apps CLIP implementation and provide guidance if missing.

## Installation

```bash
cd system_services/hailo-clip
sudo ./install.sh
```

Optional warmup (pre-loads model):

```bash
sudo ./install.sh --warmup
```

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-clip.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 5000
  debug: false

clip:
  # Model selection
  model: clip-resnet-50x4
  embedding_dimension: 640
  device: 0
  image_size: 224
  batch_size: 1

performance:
  worker_threads: 2
  request_timeout: 30
```

After changes, restart the service:

```bash
sudo systemctl restart hailo-clip.service
```

## Basic Usage

Query service health:

```bash
curl http://localhost:5000/health
```

### Classify an Image

```bash
# Prepare image
IMAGE_B64=$(base64 -w0 < image.jpg)

# Classify against prompts
curl -X POST http://localhost:5000/v1/classify \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,${IMAGE_B64}\",
    \"prompts\": [
      \"empty shelf\",
      \"stocked shelf\",
      \"product on wrong shelf\"
    ],
    \"top_k\": 1
  }"
```

### Get Image Embedding

```bash
curl -X POST http://localhost:5000/v1/embed/image \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"data:image/jpeg;base64,${IMAGE_B64}\"}"
```

### Get Text Embedding

```bash
curl -X POST http://localhost:5000/v1/embed/text \
  -H "Content-Type: application/json" \
  -d '{"text": "person wearing uniform"}'
```

Check service status:

```bash
sudo systemctl status hailo-clip.service
sudo journalctl -u hailo-clip.service -f
```

## Verification

```bash
sudo ./verify.sh
```

This checks:
- Service status
- HTTP health endpoint
- Model loading
- Basic classification

## Uninstall

```bash
sudo ./uninstall.sh
```

Optional cleanup:

```bash
sudo ./uninstall.sh --remove-user --purge-data
```

## Documentation

- **API Reference:** [API_SPEC.md](API_SPEC.md) — All REST endpoints with examples
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md) — Design, constraints, resource model
- **Troubleshooting:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues and solutions

## Use Cases

1. **Retail Monitoring**
   - Shelf stocking: `"empty shelf"` vs. `"stocked shelf"`
   - Product placement: `"product on wrong shelf"`
   - Inventory compliance

2. **Access Control**
   - Person attributes: `"person wearing uniform"`, `"person carrying prohibited item"`
   - Scene classification: `"restricted area"`

3. **Smart Home Automation**
   - Scene understanding for triggering: `"person cooking"` → activate ventilation
   - Context-aware lighting adjustments

4. **Surveillance**
   - `"unusual activity"`, `"normal scene"`, `"emergency situation"`
   - Runtime reconfiguration without model retraining

## Performance

| Metric | Typical Value |
|--------|---|
| Throughput | 20-30 fps |
| Image encode | 33-50ms |
| Text encode | 5-10ms |
| Total response | 50-150ms |
| Memory usage | 1-2 GB |
| Thermal impact | Low-Moderate |

## Integration with Other Services

CLIP can run concurrently with:
- `hailo-ollama` (LLM service on port 11434)
- `hailo-vision` (other vision services)

Total memory footprint when combined: 4-8 GB (within Pi 5 budget).

## Support

- Logs: `journalctl -u hailo-clip.service -f`
- Config: `/etc/hailo/hailo-clip.yaml`
- Status: `systemctl status hailo-clip.service`

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
