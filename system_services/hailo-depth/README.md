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
2. Configure device permissions for `/dev/hailo0`
3. Install configuration to `/etc/hailo/hailo-depth.yaml`
4. Install systemd service unit
5. Start and enable the service

### Verification

```bash
./verify.sh
```

Or manually:

```bash
sudo systemctl status hailo-depth.service
curl http://localhost:11436/health
```

### API Usage

**Health Check:**

```bash
curl http://localhost:11436/health
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

**Response:**

```json
{
  "model": "scdepthv3",
  "model_type": "monocular",
  "input_shape": [480, 640, 3],
  "depth_shape": [480, 640],
  "inference_time_ms": 42.5,
  "normalized": true,
  "depth_map": "<base64-encoded NPZ>",
  "depth_image": "<base64-encoded PNG>"
}
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
  format: "both"  # numpy, image, or both
  colormap: "viridis"
  normalize: true

resource_limits:
  memory_max: "3G"
  cpu_quota: "80%"
```

After editing, regenerate JSON config and restart:

```bash
sudo python3 /usr/local/bin/render_config.py \
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
