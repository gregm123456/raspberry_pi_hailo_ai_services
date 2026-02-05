# Hailo Depth Estimation API Specification

REST API for depth estimation inference via Hailo-10H NPU.

**Base URL:** `http://localhost:11439`  
**Default Port:** 11439  
**Protocol:** HTTP/1.1  
**Content Types:** `application/json`, `multipart/form-data`

---

## Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Description:** Service health and status information.

**Response:**

```json
{
  "status": "ok",
  "service": "hailo-depth",
  "model": "scdepthv3",
  "model_type": "monocular",
  "model_loaded": true,
  "uptime_seconds": 3642.5
}
```

**Status Codes:**
- `200 OK` - Service is healthy

---

### 2. Readiness Probe

**Endpoint:** `GET /health/ready`

**Description:** Kubernetes/systemd readiness check.

**Response (Ready):**

```json
{
  "ready": true
}
```

**Response (Not Ready):**

```json
{
  "ready": false,
  "reason": "model_loading"
}
```

**Status Codes:**
- `200 OK` - Service is ready
- `503 Service Unavailable` - Service is starting or model not loaded

---

### 3. Service Information

**Endpoint:** `GET /v1/info`

**Description:** Service capabilities and model information.

**Response:**

```json
{
  "service": "hailo-depth",
  "version": "1.0.0",
  "model": {
    "name": "scdepthv3",
    "type": "monocular",
    "loaded": true
  },
  "capabilities": {
    "monocular": true,
    "stereo": false,
    "output_formats": ["numpy", "image", "both"],
    "colormaps": ["viridis", "plasma", "magma", "turbo", "jet"]
  }
}
```

**Status Codes:**
- `200 OK` - Success

---

### 4. Depth Estimation

**Endpoint:** `POST /v1/depth/estimate`

**Description:** Perform depth estimation on an input image.

#### Request Format 1: Multipart Form Data

**Content-Type:** `multipart/form-data`

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | file | Yes | Image file (JPEG, PNG, etc.) |
| `output_format` | string | No | Output format: `numpy`, `image`, or `both` (default: config) |
| `normalize` | boolean | No | Normalize depth to 0-1 range (default: config) |
| `colormap` | string | No | Colormap for visualization: `viridis`, `plasma`, `magma`, `turbo`, `jet` (default: config) |

**Example:**

```bash
curl -X POST http://localhost:11439/v1/depth/estimate \
  -F "image=@photo.jpg" \
  -F "output_format=both" \
  -F "normalize=true" \
  -F "colormap=viridis"
```

#### Request Format 2: JSON with Base64

**Content-Type:** `application/json`

**Body:**

```json
{
  "image": "<base64-encoded image data>",
  "output_format": "both",
  "normalize": true,
  "colormap": "viridis"
}
```

**Example:**

```bash
IMAGE_B64=$(base64 -w 0 < photo.jpg)

curl -X POST http://localhost:11439/v1/depth/estimate \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"$IMAGE_B64\",
    \"output_format\": \"both\",
    \"normalize\": true,
    \"colormap\": \"viridis\"
  }"
```

#### Response

**Success (200 OK):**

```json
{
  "model": "scdepthv3",
  "model_type": "monocular",
  "input_shape": [480, 640, 3],
  "depth_shape": [480, 640],
  "inference_time_ms": 42.5,
  "normalized": true,
  "depth_map": "<base64-encoded NPZ file>",
  "depth_image": "<base64-encoded PNG image>"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Model name used for inference |
| `model_type` | string | Model type: `monocular` or `stereo` |
| `input_shape` | array | Input image shape `[height, width, channels]` |
| `depth_shape` | array | Output depth map shape `[height, width]` |
| `inference_time_ms` | float | Inference time in milliseconds |
| `normalized` | boolean | Whether depth values are normalized |
| `depth_map` | string | Base64-encoded NPZ file containing NumPy array (if `output_format` includes `numpy`) |
| `depth_image` | string | Base64-encoded PNG visualization (if `output_format` includes `image`) |

**Error Responses:**

**400 Bad Request:**

```json
{
  "error": {
    "message": "Missing 'image' field",
    "type": "invalid_request"
  }
}
```

**500 Internal Server Error:**

```json
{
  "error": {
    "message": "Depth estimation failed: <details>",
    "type": "internal_error"
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid input or missing required fields
- `500 Internal Server Error` - Inference failure

---

## Output Format Details

### NumPy Array (NPZ)

When `output_format` is `numpy` or `both`, the `depth_map` field contains a base64-encoded NPZ file.

**Decoding (Python):**

```python
import base64
import io
import numpy as np

# Decode base64
npz_bytes = base64.b64decode(response['depth_map'])

# Load NPZ
npz_buffer = io.BytesIO(npz_bytes)
depth_array = np.load(npz_buffer)['depth']

print(depth_array.shape)  # e.g., (480, 640)
print(depth_array.dtype)  # float32
```

**Array Format:**
- **Shape:** `[height, width]`
- **Data Type:** `float32`
- **Values:** Depth values (normalized to 0-1 if `normalize=true`, otherwise raw model output)

### Colorized Image (PNG)

When `output_format` is `image` or `both`, the `depth_image` field contains a base64-encoded PNG.

**Decoding (Python):**

```python
import base64
import io
from PIL import Image

# Decode base64
png_bytes = base64.b64decode(response['depth_image'])

# Load image
img_buffer = io.BytesIO(png_bytes)
depth_img = Image.open(img_buffer)

depth_img.show()  # Display
depth_img.save('depth_output.png')  # Save
```

**Image Format:**
- **Format:** PNG
- **Color:** RGB (8-bit per channel)
- **Colormap:** Applied as specified in request (default: viridis)

---

## Colormaps

Supported colormaps for depth visualization:

| Colormap | Description | Use Case |
|----------|-------------|----------|
| `viridis` | Perceptually uniform, blue→yellow | General purpose (default) |
| `plasma` | Perceptually uniform, purple→yellow | High contrast |
| `magma` | Perceptually uniform, black→white | Printable |
| `turbo` | Rainbow-like, high dynamic range | Maximum discrimination |
| `jet` | Classic rainbow, blue→red | Legacy compatibility |

---

## Rate Limiting

No rate limiting is currently enforced. For production deployments, consider adding a reverse proxy (nginx, caddy) with rate limiting.

---

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "message": "Human-readable error message",
    "type": "error_category"
  }
}
```

**Error Types:**

| Type | Description |
|------|-------------|
| `invalid_request` | Malformed request or missing required fields |
| `invalid_request_error` | Invalid parameter values |
| `internal_error` | Server-side failure (check logs) |

---

## Client Libraries

### Python

```python
import requests
import base64
import numpy as np
import io
from PIL import Image

def estimate_depth(image_path, output_format='both'):
    with open(image_path, 'rb') as f:
        response = requests.post(
            'http://localhost:11439/v1/depth/estimate',
            files={'image': f},
            data={'output_format': output_format, 'normalize': 'true'}
        )
    
    response.raise_for_status()
    return response.json()

# Usage
result = estimate_depth('photo.jpg')
print(f"Inference time: {result['inference_time_ms']} ms")

# Decode NumPy array
npz_data = io.BytesIO(base64.b64decode(result['depth_map']))
depth = np.load(npz_data)['depth']
print(f"Depth shape: {depth.shape}, range: {depth.min():.2f}-{depth.max():.2f}")

# Decode image
img_data = io.BytesIO(base64.b64decode(result['depth_image']))
depth_img = Image.open(img_data)
depth_img.save('depth_visualization.png')
```

### Bash (curl)

```bash
#!/bin/bash

IMAGE_PATH="$1"
OUTPUT_DIR="output"

mkdir -p "${OUTPUT_DIR}"

# Perform depth estimation
RESPONSE=$(curl -sS -X POST http://localhost:11439/v1/depth/estimate \
  -F "image=@${IMAGE_PATH}" \
  -F "output_format=both" \
  -F "normalize=true" \
  -F "colormap=viridis")

# Extract depth image
echo "${RESPONSE}" | jq -r '.depth_image' | base64 -d > "${OUTPUT_DIR}/depth.png"

# Extract inference time
INFERENCE_MS=$(echo "${RESPONSE}" | jq -r '.inference_time_ms')
echo "Inference time: ${INFERENCE_MS} ms"
echo "Depth visualization saved to ${OUTPUT_DIR}/depth.png"
```

---

## Performance Considerations

- **Input Size:** Larger images take longer to process (resized to model input size)
- **Output Format:** `numpy` is faster than `image` (no colormap rendering)
- **Concurrent Requests:** Service handles one request at a time; queue additional requests
- **Model Loading:** First request after startup may be slower (model initialization)

---

## Versioning

Current API version: **v1**

Version is included in endpoint paths (`/v1/*`). Future breaking changes will increment the version.

---

## Support

For issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
