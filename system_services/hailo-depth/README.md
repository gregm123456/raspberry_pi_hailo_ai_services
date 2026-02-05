# Hailo Depth Estimation Service

Monocular and stereo depth estimation as a managed system service on Raspberry Pi 5 with Hailo-10H NPU.

## Overview

The `hailo-depth` service provides depth estimation inference via a REST API, utilizing the Hailo-10H AI accelerator for high-performance depth mapping. The service supports monocular depth estimation using the SCDepthV3 model.

**Key Features:**
- Monocular depth estimation (SCDepthV3 model)
- REST API for image upload and depth map retrieval
- Multiple output formats: NumPy arrays, colorized images, or both
- Persistent model loading for low latency
- systemd integration for automatic startup and recovery
- Resource management and thermal awareness

## Quick Start

### Prerequisites

- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie or later)
- Hailo driver installed: `sudo apt install dkms hailo-h10-all`
- Python 3.10+ with required packages

### Installation

```bash
cd /path/to/system_services/hailo-depth
sudo ./install.sh
```

The installer will:
1. Create system user and group (`hailo-depth`)
2. Create isolated Python venv at `/opt/hailo-depth/venv`
3. Install dependencies (aiohttp, numpy, pillow, etc.) into venv
4. Vendor hailo-apps submodule to `/opt/hailo-depth/vendor/hailo-apps`
5. Configure device permissions for `/dev/hailo0`
6. Create state directories: `/var/lib/hailo-depth/resources/{models,postprocess}/`
7. Install configuration to `/etc/hailo/hailo-depth.yaml`
8. Render JSON config to `/etc/xdg/hailo-depth/hailo-depth.json`
9. Install and enable systemd service

**Important:** The installer creates placeholders for model artifacts. You must download `scdepthv3.hef` and place it in `/var/lib/hailo-depth/resources/models/`. See [MODEL_ACQUISITION.md](MODEL_ACQUISITION.md) for download instructions.

### Verification

```bash
./verify.sh
```

Or manually:

```bash
sudo systemctl status hailo-depth.service
curl http://localhost:11436/health
curl http://localhost:11436/v1/info
```

### API Usage

**Health Check:**

```bash
curl http://localhost:11436/health
```

**Service Info:**

```bash
curl http://localhost:11436/v1/info
```

**Depth Estimation (multipart form):**

```bash
curl -X POST http://localhost:11436/v1/depth/estimate \
  -F "image=@/path/to/image.jpg" \
  -F "output_format=both" \
  -F "colormap=viridis"
```

**Depth Estimation (JSON with base64):**

```bash
# Encode image
IMAGE_B64=$(base64 -w 0 < image.jpg)

# Send request
curl -X POST http://localhost:11436/v1/depth/estimate \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"$IMAGE_B64\",
    \"output_format\": \"both\",
    \"normalize\": true,
    \"colormap\": \"viridis\"
  }"
```

**Depth Estimation (JSON with image URL):**

```bash
curl -X POST http://localhost:11436/v1/depth/estimate \
  -H "Content-Type: application/json" \
  -d "{
    \"image_url\": \"https://example.com/image.jpg\",
    \"output_format\": \"both\",
    \"normalize\": true
  }"
```

**Response:**

```json
{
  "model": "scdepthv3",
  "model_type": "monocular",
  "input_shape": [480, 640, 3],
  "depth_shape": [480, 640],
  "inference_time_ms": 42.5,
  "normalized": true,
  "stats": {
    "min": 0.05,
    "max": 0.95,
    "mean": 0.42,
    "p95": 0.89
  },
  "depth_map": "<base64-encoded NPZ>",
  "depth_image": "<base64-encoded PNG>"
}
```

**Output Formats:**
- `numpy`: Base64-encoded NPZ file with `depth` array (NumPy format)
- `image`: Base64-encoded colorized PNG using specified colormap
- `both`: Both NumPy and image outputs
- `depth_png_16`: 16-bit grayscale PNG (high precision, smaller than numpy)

## Project Structure

After installation, the service consists of:

**Service Code & Runtime:**
```
/opt/hailo-depth/
├── venv/                           # Isolated Python environment
│   └── bin/python                 # Service Python executable
├── vendor/hailo-apps/             # Vendored hailo-apps submodule
├── hailo_depth_server.py          # Main service script
└── render_config.py               # Config YAML → JSON converter
```

**Configuration:**
```
/etc/hailo/
└── hailo-depth.yaml               # User-editable config (YAML)

/etc/xdg/hailo-depth/
└── hailo-depth.json               # Runtime config (JSON, auto-rendered)
```

**State & Resources:**
```
/var/lib/hailo-depth/
├── resources/
│   ├── models/                    # HEF model files
│   │   └── scdepthv3.hef
│   └── postprocess/               # Postprocess libraries
├── cache/                         # Temporary inference data
└── hailo-depth.state              # systemd state file
```

**System Integration:**
```
/etc/systemd/system/
└── hailo-depth.service            # systemd service unit
```

## Configuration

Edit `/etc/hailo/hailo-depth.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11436

model:
  name: "scdepthv3"
  type: "monocular"
  keep_alive: -1  # Persistent loading

output:
  format: "both"  # numpy, image, both, or depth_png_16
  colormap: "viridis"  # viridis, plasma, magma, turbo, jet
  normalize: true
  include_stats: true
  depth_png_16: false

input:
  allow_local_paths: false  # Security: disable by default
  allow_image_url: true
  max_image_mb: 50

resources:
  model_dir: /var/lib/hailo-depth/resources/models
  postprocess_dir: /var/lib/hailo-depth/resources/postprocess

resource_limits:
  memory_max: "3G"
  cpu_quota: "80%"
```

After editing, regenerate JSON config and restart:

```bash
cd /path/to/system_services/hailo-depth
sudo python3 render_config.py \
  --input /etc/hailo/hailo-depth.yaml \
  --output /etc/xdg/hailo-depth/hailo-depth.json

sudo systemctl restart hailo-depth.service
```

## Operation

### Service Management

```bash
# Start/stop/restart
sudo systemctl start hailo-depth.service
sudo systemctl stop hailo-depth.service
sudo systemctl restart hailo-depth.service

# View logs
sudo journalctl -u hailo-depth.service -f

# Check status
sudo systemctl status hailo-depth.service
```

### Uninstallation

```bash
cd /path/to/system_services/hailo-depth
sudo ./uninstall.sh
```

## Use Cases

- **Robotics:** Obstacle avoidance, navigation, SLAM
- **AR/VR:** Scene understanding, spatial computing
- **Photography:** Depth-of-field effects, 3D reconstruction
- **Safety:** Proximity detection, collision warning

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design details.

## API Reference

See [API_SPEC.md](API_SPEC.md) for complete API documentation.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## Development

### Testing

Integration tests are located in `tests/`:

```bash
cd tests
pytest test_hailo_depth_service.py -v
```

### Python Client Example

```python
import requests
import numpy as np
import io
from PIL import Image

# Load image
with open('image.jpg', 'rb') as f:
    image_data = f.read()

# Send request
response = requests.post(
    'http://localhost:11436/v1/depth/estimate',
    files={'image': image_data},
    data={'output_format': 'both', 'normalize': 'true'}
)

result = response.json()

# Decode depth map
depth_npz = io.BytesIO(base64.b64decode(result['depth_map']))
depth_array = np.load(depth_npz)['depth']

# Decode visualization
depth_png = io.BytesIO(base64.b64decode(result['depth_image']))
depth_vis = Image.open(depth_png)
depth_vis.show()

print(f"Inference time: {result['inference_time_ms']} ms")
print(f"Depth range: {depth_array.min():.2f} - {depth_array.max():.2f}")
```

## Performance

On Raspberry Pi 5 with Hailo-10H:

- **SCDepthV3:** ~40-60ms inference (640x480)
- **Memory:** ~2-3GB resident
- **Concurrent Services:** Can run alongside hailo-vision, hailo-ollama, etc.

## Limitations

- **Monocular Depth:** Relative depth values (not absolute distances)
- **Resolution:** Input images resized to model input size (typically 640x480)
- **Scale Ambiguity:** Depth scale is scene-dependent
- **Stereo:** Not yet implemented (future enhancement)

## License

See repository root for license information.

## References

- [SCDepthV3 Paper](https://arxiv.org/abs/2211.03660)
- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo)
- [Hailo Apps Infrastructure](https://github.com/hailo-ai/hailo-apps-infra)
