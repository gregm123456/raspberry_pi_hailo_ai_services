# Hailo SCRFD Service

Deploys SCRFD face detection with 5-point facial landmarks as a managed systemd service on Raspberry Pi 5 with Hailo-10H, exposing a REST API on port 5001.

## Features

- **Face Detection:** Detect faces at multiple scales with high accuracy
- **Facial Landmarks:** 5-point landmarks (eyes, nose, mouth corners)
- **Face Alignment:** Automatic face alignment for face recognition pipelines
- **Hailo-accelerated:** Optimized for Hailo-10H NPU (50-60 fps with lightweight model)
- **RESTful API:** Clean JSON interface for integration
- **Multi-face Support:** Detect multiple faces in single image
- **Configurable Thresholds:** Adjust confidence and NMS thresholds

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- Python dependencies:
  ```bash
  sudo apt install python3-yaml python3-numpy python3-pil python3-flask
  pip3 install opencv-python
  ```

The installer will check for the hailo-apps SCRFD postprocessing implementation.

## Installation

```bash
cd system_services/hailo-scrfd
sudo ./install.sh
```

Optional warmup (pre-loads model):

```bash
sudo ./install.sh --warmup
```

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-scrfd.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 5001
  debug: false

scrfd:
  # Model: scrfd_2.5g_bnkps (lightweight) or scrfd_10g_bnkps (high accuracy)
  model: scrfd_2.5g_bnkps
  input_size: 640
  device: 0
  conf_threshold: 0.5
  nms_threshold: 0.4

detection:
  return_landmarks: true
  max_faces: 10

alignment:
  output_size: 112  # Standard for ArcFace

performance:
  worker_threads: 2
  request_timeout: 30
```

After changes, restart the service:

```bash
sudo systemctl restart hailo-scrfd.service
```

## Basic Usage

Query service health:

```bash
curl http://localhost:5001/health
```

### Detect Faces

```bash
# Prepare image
IMAGE_B64=$(base64 -w0 < photo.jpg)

# Detect faces with landmarks
curl -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,${IMAGE_B64}\",
    \"return_landmarks\": true,
    \"conf_threshold\": 0.5
  }"
```

Response:
```json
{
  "faces": [
    {
      "bbox": [120, 80, 200, 250],
      "confidence": 0.95,
      "landmarks": [
        {"type": "left_eye", "x": 160, "y": 140},
        {"type": "right_eye", "x": 220, "y": 140},
        {"type": "nose", "x": 190, "y": 180},
        {"type": "left_mouth", "x": 170, "y": 230},
        {"type": "right_mouth", "x": 210, "y": 230}
      ]
    }
  ],
  "num_faces": 1,
  "inference_time_ms": 18
}
```

### Get Annotated Image

```bash
curl -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,${IMAGE_B64}\",
    \"annotate\": true
  }" | jq -r '.annotated_image' > annotated.txt

# Extract and view
cat annotated.txt | cut -d',' -f2 | base64 -d > annotated.jpg
```

### Align Faces for Recognition

```bash
curl -X POST http://localhost:5001/v1/align \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"data:image/jpeg;base64,${IMAGE_B64}\"}"
```

Returns aligned face crops (112×112) ready for ArcFace embedding.

Check service status:

```bash
sudo systemctl status hailo-scrfd.service
sudo journalctl -u hailo-scrfd.service -f
```

## Verification

```bash
sudo ./verify.sh
```

This checks:
- Service status
- HTTP health endpoint
- Face detection functionality
- Log errors

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

1. **Face Recognition Pipeline**
   - Detect faces → Align faces → Extract embeddings (ArcFace) → Compare
   - See `hailo-face` service for full face recognition system

2. **Access Control**
   - Real-time face detection at entry points
   - Quality checks (confidence, landmark visibility)
   - Face tracking across camera feeds

3. **Photo Management**
   - Automatic face detection in photo libraries
   - Face clustering for organization
   - Thumbnail generation with face cropping

4. **Video Analytics**
   - Count people in scenes
   - Track face appearances over time
   - Demographic analysis (with additional models)

5. **Augmented Reality**
   - Face filters using landmark positions
   - Virtual makeup try-on
   - Face swapping applications

## Model Comparison

| Model | GFLOPs | Throughput | AP (WIDER FACE) | Best For |
|-------|--------|-----------|-----------------|----------|
| **SCRFD-2.5G** | 2.5 | 50-60 fps | 82% | Real-time, resource-constrained |
| **SCRFD-10G** | 10 | 30-40 fps | 92% | High accuracy requirements |

## Performance

| Metric | SCRFD-2.5G | SCRFD-10G |
|--------|-----------|-----------|
| Throughput | 50-60 fps | 30-40 fps |
| Latency | 16-20ms | 25-33ms |
| Memory usage | 1-1.5 GB | 1.5-2 GB |
| Thermal impact | Low | Low-Moderate |

## Landmark Order

The 5 landmarks are returned in this order:
1. **Left eye center** (subject's left)
2. **Right eye center** (subject's right)
3. **Nose tip**
4. **Left mouth corner**
5. **Right mouth corner**

## Integration with Other Services

SCRFD can run concurrently with:
- `hailo-clip` (CLIP service on port 5000)
- `hailo-vision` (general vision service)
- `hailo-ollama` (LLM service on port 11434)
- `hailo-face` (ArcFace embeddings for face recognition)

Typical pipeline:
```
hailo-scrfd (detect & align) → hailo-face (embed) → Database (match)
```

## Support

- Logs: `journalctl -u hailo-scrfd.service -f`
- Config: `/etc/hailo/hailo-scrfd.yaml`
- Status: `systemctl status hailo-scrfd.service`

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
