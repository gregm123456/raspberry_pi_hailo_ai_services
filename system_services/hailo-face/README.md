# Hailo Face Recognition Service

REST API service for Hailo-10H face detection and MiVOLO age/gender estimates, with prototype identity-management endpoints.

## Features

- **Face Attributes:** SCRFD detection, landmarks, and MiVOLO age/gender estimates
- **Embedding Extraction:** Generate 512-dimensional face embeddings using ArcFace
- **Face Recognition:** Match faces against a database of known identities
- **Identity Management:** Add, remove, and list known identities
- **Persistent Database:** SQLite storage for face embeddings
- **Hailo-10H Accelerated:** Face attribute inference via the Device Manager

The `/v1/attributes` endpoint is the verified Hailo-10H path. The existing
embedding and identity-recognition endpoints remain prototype code and still
use mock inference; do not use those endpoints as real biometric recognition.

## Architecture

The Flask REST API's verified `/v1/attributes` path uses the Hailo-10H
**SCRFD-2.5G** model (`scrfd_2.5g_384_640.hef`) with MiVOLO for age/gender
estimates. The `2.5G` designation describes the model's compute tier, not its
HEF file size; the compiled HEF is approximately 245 MB.

The separate embedding and identity-recognition endpoints are prototypes that
still use mock inference. Their legacy `face_recognition.detection_model`
setting may say `scrfd_10g`, but it does not select or load the model used by
`/v1/attributes`.

- **Face attributes:** SCRFD-2.5G + MiVOLO
- **Prototype recognition:** ArcFace MobileFaceNet configuration; inference is mocked
- **Database:** SQLite for persistent identity storage
- **systemd Integration:** Managed service with automatic restart

## Prerequisites

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- Hailo Device Manager installed and running (`hailo-device-mgr` socket group)
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
3. Download public v5.5.0 Hailo-10H SCRFD and MiVOLO HEFs to
   `/var/lib/hailo-face/models/` (no Developer Zone login required)
4. Render configuration to `/etc/hailo/hailo-face.yaml`
5. Set up database at `/var/lib/hailo-face/faces.db`
6. Install and start systemd service

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

### Face Attributes
```bash
curl -X POST http://localhost:5002/v1/attributes \
  -H "Content-Type: application/json" \
  -d '{"image":"data:image/jpeg;base64,..."}'
```

Returns face boxes, landmarks, face crops, age estimates, and male/female
scores. These are model estimates, not verified attributes.

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

face_attributes:
  enabled: true
  scrfd_hef: /var/lib/hailo-face/models/scrfd_2.5g_384_640.hef
  mivolo_hef: /var/lib/hailo-face/models/mivolo_d1.hef
  score_threshold: 0.5
  nms_threshold: 0.4
  max_faces: 10

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
