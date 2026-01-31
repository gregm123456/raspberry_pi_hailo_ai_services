# Hailo SCRFD API Specification

REST API for face detection with 5-point facial landmarks using SCRFD model on Hailo-10H.

**Base URL:** `http://localhost:5001`

---

## Endpoints

### 1. Health Check

**GET** `/health`

Check service health and status.

#### Response

```json
{
  "status": "healthy",
  "service": "hailo-scrfd",
  "model_loaded": true,
  "model": "scrfd_2.5g_bnkps"
}
```

**Status Codes:**
- `200 OK` — Service is healthy
- `503 Service Unavailable` — Service is unhealthy

---

### 2. Detect Faces

**POST** `/v1/detect`

Detect faces in an image with bounding boxes and facial landmarks.

#### Request Body

```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "return_landmarks": true,
  "conf_threshold": 0.5,
  "annotate": false
}
```

**Parameters:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `image` | string | Yes | — | Base64-encoded image (with or without data URI prefix) |
| `image_url` | string | No | — | URL to image (not yet implemented) |
| `return_landmarks` | boolean | No | `true` | Include 5-point facial landmarks |
| `conf_threshold` | float | No | `0.5` | Minimum confidence threshold (0.0-1.0) |
| `annotate` | boolean | No | `false` | Return annotated image with bounding boxes and landmarks |

#### Response

```json
{
  "faces": [
    {
      "bbox": [120, 80, 200, 250],
      "confidence": 0.952,
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
  "inference_time_ms": 18.5,
  "model": "scrfd_2.5g_bnkps",
  "annotated_image": "data:image/jpeg;base64,..." 
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `faces` | array | Array of detected face objects |
| `faces[].bbox` | [int, int, int, int] | Bounding box [x, y, width, height] |
| `faces[].confidence` | float | Detection confidence score (0.0-1.0) |
| `faces[].landmarks` | array | 5 facial landmarks (if `return_landmarks=true`) |
| `faces[].landmarks[].type` | string | Landmark type name |
| `faces[].landmarks[].x` | int | X coordinate |
| `faces[].landmarks[].y` | int | Y coordinate |
| `num_faces` | int | Total number of faces detected |
| `inference_time_ms` | float | Inference time in milliseconds |
| `model` | string | Model name used |
| `annotated_image` | string | Base64-encoded annotated image (if `annotate=true`) |

**Status Codes:**
- `200 OK` — Success
- `400 Bad Request` — Invalid request (missing image, invalid parameters)
- `500 Internal Server Error` — Inference error

---

### 3. Align Faces

**POST** `/v1/align`

Detect faces and return aligned face crops suitable for face recognition.

Performs similarity transformation based on 5-point landmarks to normalize face orientation.

#### Request Body

```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | Yes | Base64-encoded image |
| `image_url` | string | No | URL to image (not yet implemented) |

#### Response

```json
{
  "faces": [
    {
      "face_id": 0,
      "bbox": [120, 80, 200, 250],
      "confidence": 0.952,
      "aligned_image": "data:image/jpeg;base64,..."
    }
  ],
  "num_faces": 1,
  "model": "scrfd_2.5g_bnkps"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `faces` | array | Array of aligned face objects |
| `faces[].face_id` | int | Face index in detection order |
| `faces[].bbox` | [int, int, int, int] | Original bounding box |
| `faces[].confidence` | float | Detection confidence |
| `faces[].aligned_image` | string | Base64-encoded aligned face image (112×112 by default) |
| `num_faces` | int | Total number of faces |
| `model` | string | Model name used |

**Aligned Image Properties:**
- Size: 112×112 pixels (configurable in config.yaml)
- Format: RGB
- Aligned to standard face template for recognition models (ArcFace, etc.)

**Status Codes:**
- `200 OK` — Success
- `400 Bad Request` — Invalid request
- `500 Internal Server Error` — Processing error

---

## Data Formats

### Image Input

**Base64 Encoding:**
```bash
# Encode image to base64
IMAGE_B64=$(base64 -w0 < photo.jpg)

# Use in request
curl -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"data:image/jpeg;base64,${IMAGE_B64}\"}"
```

**Data URI format (optional):**
- With prefix: `data:image/jpeg;base64,/9j/4AAQ...`
- Without prefix: `/9j/4AAQ...` (base64 only)

Both formats are accepted.

### Bounding Box Format

Bounding boxes use **[x, y, width, height]** format:
- `x`: Left edge x-coordinate
- `y`: Top edge y-coordinate
- `width`: Box width
- `height`: Box height

Origin is top-left corner of image.

### Landmark Order

The 5 landmarks are always in this order:
1. **Left eye center** — Subject's left eye
2. **Right eye center** — Subject's right eye
3. **Nose tip** — Nose center point
4. **Left mouth corner** — Subject's left mouth corner
5. **Right mouth corner** — Subject's right mouth corner

---

## Error Responses

All errors return JSON with an `error` field:

```json
{
  "error": "Error description"
}
```

**Common Errors:**

| Status | Error | Cause |
|--------|-------|-------|
| `400` | `No JSON body` | Missing request body |
| `400` | `Failed to decode image` | Invalid base64 or image format |
| `400` | `Missing or invalid 'image' field` | Image field not provided |
| `500` | `Failed to detect faces` | Inference error |
| `500` | `Failed to encode image` | Image processing error |
| `503` | `Model not loaded` | Service not ready |

---

## Usage Examples

### Example 1: Basic Face Detection

```bash
#!/bin/bash

IMAGE_B64=$(base64 -w0 < photo.jpg)

curl -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,${IMAGE_B64}\",
    \"conf_threshold\": 0.6,
    \"return_landmarks\": true
  }" | jq .
```

### Example 2: Get Annotated Image

```bash
#!/bin/bash

IMAGE_B64=$(base64 -w0 < photo.jpg)

# Get annotated image
RESPONSE=$(curl -s -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,${IMAGE_B64}\",
    \"annotate\": true
  }")

# Extract annotated image
echo "$RESPONSE" | jq -r '.annotated_image' | cut -d',' -f2 | base64 -d > annotated.jpg

echo "Annotated image saved to annotated.jpg"
```

### Example 3: Face Alignment for Recognition

```bash
#!/bin/bash

IMAGE_B64=$(base64 -w0 < photo.jpg)

# Get aligned face crops
RESPONSE=$(curl -s -X POST http://localhost:5001/v1/align \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"data:image/jpeg;base64,${IMAGE_B64}\"}")

# Extract first aligned face
echo "$RESPONSE" | jq -r '.faces[0].aligned_image' | cut -d',' -f2 | base64 -d > aligned_face_0.jpg

NUM_FACES=$(echo "$RESPONSE" | jq '.num_faces')
echo "Found ${NUM_FACES} faces. First face saved to aligned_face_0.jpg"
```

### Example 4: Python Client

```python
import base64
import requests
from pathlib import Path

def detect_faces(image_path: str, conf_threshold: float = 0.5):
    """Detect faces in an image."""
    
    # Read and encode image
    image_bytes = Path(image_path).read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    # Request
    response = requests.post(
        'http://localhost:5001/v1/detect',
        json={
            'image': f'data:image/jpeg;base64,{image_b64}',
            'conf_threshold': conf_threshold,
            'return_landmarks': True,
        }
    )
    response.raise_for_status()
    
    result = response.json()
    print(f"Found {result['num_faces']} faces in {result['inference_time_ms']:.1f}ms")
    
    for i, face in enumerate(result['faces']):
        print(f"  Face {i}: bbox={face['bbox']}, confidence={face['confidence']:.3f}")
        if 'landmarks' in face:
            for lm in face['landmarks']:
                print(f"    {lm['type']}: ({lm['x']}, {lm['y']})")
    
    return result

# Usage
result = detect_faces('photo.jpg', conf_threshold=0.6)
```

---

## Configuration

Service configuration is in `/etc/hailo/hailo-scrfd.yaml`:

```yaml
scrfd:
  model: scrfd_2.5g_bnkps  # or scrfd_10g_bnkps
  conf_threshold: 0.5
  nms_threshold: 0.4
  input_size: 640

detection:
  return_landmarks: true
  max_faces: 10

alignment:
  output_size: 112
```

Restart service after config changes:
```bash
sudo systemctl restart hailo-scrfd.service
```

---

## Performance

**SCRFD-2.5G (Lightweight):**
- Throughput: 50-60 fps
- Latency: 16-20ms per image
- Memory: 1-1.5 GB

**SCRFD-10G (High Accuracy):**
- Throughput: 30-40 fps
- Latency: 25-33ms per image
- Memory: 1.5-2 GB

---

## See Also

- [README.md](README.md) — Installation and usage guide
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues
