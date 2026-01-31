# Hailo Face Recognition Service

REST API service for face detection, recognition, and identity management using Hailo-10H NPU acceleration on Raspberry Pi 5.

## Features

- **Face Detection:** Detect faces with bounding boxes and confidence scores
- **Embedding Extraction:** Generate 512-dimensional face embeddings using ArcFace
- **Face Recognition:** Match faces against a database of known identities
- **Identity Management:** Add, remove, and list known identities
- **Persistent Database:** SQLite storage for face embeddings
- **Hailo-10H Accelerated:** Hardware-accelerated inference on NPU

## Architecture

The service wraps Hailo's face recognition pipeline with a Flask REST API and provides:
- **Detection Model:** SCRFD-10G or RetinaFace for face detection
- **Recognition Model:** ArcFace MobileFaceNet for embedding extraction
- **Database:** SQLite for persistent identity storage
- **systemd Integration:** Managed service with automatic restart

## Prerequisites

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- Hailo kernel driver installed:
  ```bash
  sudo apt install dkms hailo-h10-all
  sudo reboot
  hailortcli fw-control identify  # Verify
  ```

## Installation

```bash
cd system_services/hailo-face
sudo ./install.sh
```

The installer will:
1. Create `hailo-face` system user
2. Install service files to `/opt/hailo-face/`
3. Render configuration to `/etc/hailo/hailo-face.yaml`
4. Set up database at `/var/lib/hailo-face/faces.db`
5. Install and start systemd service

## Verification

```bash
./verify.sh
```

Or manually:
```bash
sudo systemctl status hailo-face
curl http://localhost:5002/health
```

## API Endpoints

### Health Check
```bash
curl http://localhost:5002/health
```

### Face Detection
```bash
curl -X POST http://localhost:5002/v1/detect \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,..."
  }'
```

### Face Embedding
```bash
curl -X POST http://localhost:5002/v1/embed \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,...",
    "bbox": [x, y, width, height]
  }'
```

### Face Recognition
```bash
curl -X POST http://localhost:5002/v1/recognize \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,...",
    "threshold": 0.5
  }'
```

### Add Identity
```bash
curl -X POST http://localhost:5002/v1/database/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "image": "data:image/jpeg;base64,..."
  }'
```

### Remove Identity
```bash
curl -X POST http://localhost:5002/v1/database/remove \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe"}'
```

### List Identities
```bash
curl http://localhost:5002/v1/database/list
```

## Configuration

Edit `/etc/hailo/hailo-face.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 5002

face_recognition:
  detection_model: scrfd_10g
  recognition_model: arcface_mobilefacenet
  detection_threshold: 0.6
  recognition_threshold: 0.5
  max_faces: 10
  database_path: /var/lib/hailo-face/database

database:
  enabled: true
  db_file: /var/lib/hailo-face/faces.db
```

Restart after changes:
```bash
sudo systemctl restart hailo-face
```

## Service Management

```bash
# Status
sudo systemctl status hailo-face

# Logs
sudo journalctl -u hailo-face -f

# Restart
sudo systemctl restart hailo-face

# Stop
sudo systemctl stop hailo-face

# Disable
sudo systemctl disable hailo-face
```

## Uninstallation

```bash
sudo ./uninstall.sh
```

This will:
- Stop and disable the service
- Remove service files
- Optionally delete database and config

## Resource Usage

- **Memory:** ~2-3GB (includes models)
- **CPU:** <80% (configurable)
- **Startup Time:** 30-60 seconds (model loading)
- **Inference Time:** 50-150ms per image

## Concurrent Services

Can run alongside other Hailo services (hailo-clip, hailo-vision, etc.) with proper memory budgeting.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## API Reference

See [API_SPEC.md](API_SPEC.md) for complete API documentation.

## Architecture Details

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and implementation details.

## License

See repository root LICENSE file.
