# Hailo Pose Estimation Service

YOLOv8-based human pose estimation service running on Hailo-10H NPU. Detects human keypoints and skeleton connections in COCO format via REST API.

## Overview

This service wraps YOLOv8-pose for real-time pose estimation on Raspberry Pi 5 with Hailo AI HAT+ 2. It provides:

- **COCO Keypoint Detection:** 17 body keypoints per person
- **Skeleton Connections:** Joint relationships for visualization
- **REST API:** Simple HTTP interface for image-based inference
- **Persistent Model Loading:** Model loads at service startup and stays resident
- **systemd Integration:** Managed as a system service with automatic restart

## Quick Start

### Prerequisites

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- Hailo driver installed:
  ```bash
  sudo apt install dkms hailo-h10-all
  sudo reboot
  hailortcli fw-control identify  # Verify installation
  ```

### Installation

```bash
cd system_services/hailo-pose
sudo ./install.sh
```

This will:
- Create `hailo-pose` system user and group
- Install service to `/opt/hailo-pose/` (venv + vendored hailo-apps)
- Install systemd unit to `/etc/systemd/system/hailo-pose.service`
- Create config at `/etc/hailo/hailo-pose.yaml`
- Start and enable the service

### Verification

```bash
./verify.sh
```

Check service status:
```bash
sudo systemctl status hailo-pose.service
sudo journalctl -u hailo-pose.service -f
```

### Basic Usage

Test with an image file:
```bash
# Using multipart/form-data
curl -X POST http://localhost:11440/v1/pose/detect \
  -F "image=@person.jpg"

# Using base64-encoded image
base64 person.jpg | tr -d '\n' > person.b64
curl -X POST http://localhost:11440/v1/pose/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$(cat person.b64)\"}"
```

Response format:
```json
{
  "poses": [
    {
      "person_id": 0,
      "bbox": {"x": 100, "y": 50, "width": 200, "height": 400},
      "bbox_confidence": 0.92,
      "keypoints": [
        {"name": "nose", "x": 150, "y": 100, "confidence": 0.95},
        {"name": "left_eye", "x": 145, "y": 95, "confidence": 0.93},
        ...
      ],
      "skeleton": [
        {"from": "nose", "to": "left_eye", "from_index": 0, "to_index": 1},
        ...
      ]
    }
  ],
  "count": 1,
  "inference_time_ms": 45,
  "image_size": {"width": 640, "height": 480}
}
```

## Configuration

Edit `/etc/hailo/hailo-pose.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11440

model:
  name: "yolov8s_pose"
  keep_alive: -1  # -1 = persistent, 0 = unload after request

inference:
  confidence_threshold: 0.5
  iou_threshold: 0.45
  max_detections: 10
  input_size: [640, 640]

pose:
  keypoint_threshold: 0.3
  skeleton_connections: true
```

After editing, re-render the JSON config and restart:
```bash
sudo /opt/hailo-pose/venv/bin/python3 /opt/hailo-pose/render_config.py \
  --input /etc/hailo/hailo-pose.yaml \
  --output /etc/xdg/hailo-pose/hailo-pose.json
sudo systemctl restart hailo-pose.service
```

## API Documentation

See [API_SPEC.md](./API_SPEC.md) for complete API reference.

Key endpoints:
- `GET /health` - Service health check
- `GET /health/ready` - Readiness probe
- `GET /v1/models` - List available models
- `POST /v1/pose/detect` - Detect poses in image

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for design details.

Key characteristics:
- **Model Lifecycle:** Persistent loading (model stays resident in memory)
- **Memory Budget:** ~1.5-2GB (YOLOv8s_pose)
- **Inference Latency:** ~30-60ms per image (640x640)
- **Throughput:** ~15-25 FPS on Pi 5
- **Concurrent Services:** Can run alongside other Hailo services

## Troubleshooting

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues.

Quick checks:
```bash
# Check service status
sudo systemctl status hailo-pose.service

# View logs
sudo journalctl -u hailo-pose.service -n 100 --no-pager

# Verify Hailo device
ls -l /dev/hailo0
hailortcli fw-control identify

# Test health endpoint
curl http://localhost:11440/health
```

## Uninstallation

```bash
cd system_services/hailo-pose
sudo ./uninstall.sh
```

This will:
- Stop and disable the service
- Remove systemd unit and binary
- Optionally remove config and data directories
- Remove service user and group

## Development

### Testing

```bash
cd tests
pytest test_hailo_pose_service.py -v
```

### Manual Testing

1. Start service locally:
   ```bash
   python3 hailo_pose_service.py
   ```

2. Test with sample image:
   ```bash
   curl -X POST http://localhost:11440/v1/pose/detect \
     -F "image=@test_image.jpg" | jq
   ```

## Performance Tuning

### Memory Optimization

Edit systemd unit or create drop-in override:
```bash
sudo systemctl edit hailo-pose.service
```

Add:
```ini
[Service]
MemoryMax=1.5G
CPUQuota=60%
```

### Model Selection

Available YOLOv8-pose variants:
- `yolov8n_pose` - Nano (fastest, lowest accuracy)
- `yolov8s_pose` - Small (balanced, default)
- `yolov8m_pose` - Medium (slower, better accuracy)
- `yolov8l_pose` - Large (requires more memory)

Update `model.name` in `/etc/hailo/hailo-pose.yaml` and restart.

## Resource Requirements

| Variant | Memory | Latency | FPS | Accuracy |
|---------|--------|---------|-----|----------|
| yolov8n | ~800MB | 20ms | 30+ | Good |
| yolov8s | ~1.5GB | 45ms | 20+ | Better |
| yolov8m | ~2.5GB | 80ms | 12+ | Best |

## License

See repository root LICENSE file.

## References

- YOLOv8 Pose: https://docs.ultralytics.com/tasks/pose/
- COCO Keypoint Format: https://cocodataset.org/#keypoints-2020
- Hailo Developer Zone: https://hailo.ai/developer-zone/
