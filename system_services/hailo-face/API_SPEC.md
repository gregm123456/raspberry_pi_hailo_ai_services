# Hailo Face Recognition API Specification

REST API for face detection, embedding extraction, recognition, and identity management.

**Base URL:** `http://localhost:5002`

**Protocol:** REST  
**Format:** JSON  
**Authentication:** None (internal service)

---

## Endpoints

### Health Check

Check service health and model status.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "service": "hailo-face",
  "model_loaded": true,
  "detection_model": "scrfd_10g",
  "recognition_model": "arcface_mobilefacenet",
  "database_enabled": true
}
```

**Status Codes:**
- `200 OK` - Service is healthy

---

### Detect Faces

Detect faces in an image with bounding boxes.

**Endpoint:** `POST /v1/detect`

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "return_landmarks": false
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | Yes | Base64-encoded image with data URI prefix |
| `return_landmarks` | boolean | No | Include facial landmarks (5 points) |

**Response:**
```json
{
  "faces": [
    {
      "bbox": [120, 85, 180, 220],
      "confidence": 0.95,
      "landmarks": null
    }
  ],
  "count": 1,
  "inference_time_ms": 45.2
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `faces` | array | List of detected faces |
| `faces[].bbox` | array | Bounding box [x, y, width, height] |
| `faces[].confidence` | float | Detection confidence (0.0-1.0) |
| `faces[].landmarks` | array | Optional 5-point landmarks [[x,y], ...] |
| `count` | int | Number of faces detected |
| `inference_time_ms` | float | Inference duration in milliseconds |

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid image or parameters
- `500 Internal Server Error` - Inference failure

---

### Extract Face Embedding

Extract 512-dimensional face embedding from an image.

**Endpoint:** `POST /v1/embed`

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "bbox": [120, 85, 180, 220]
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | Yes | Base64-encoded image |
| `bbox` | array | No | Face bounding box [x, y, w, h]. Auto-detected if omitted. |

**Response:**
```json
{
  "embedding": [0.1234, -0.5678, ...],
  "dimension": 512,
  "bbox": [120, 85, 180, 220]
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `embedding` | array | 512-dimensional float array |
| `dimension` | int | Embedding dimension (512) |
| `bbox` | array | Bounding box used for extraction |

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - No face detected or invalid bbox
- `500 Internal Server Error` - Extraction failure

---

### Recognize Faces

Recognize faces in an image by matching against database.

**Endpoint:** `POST /v1/recognize`

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "threshold": 0.5
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | Yes | Base64-encoded image |
| `threshold` | float | No | Recognition threshold (0.0-1.0). Default: 0.5 |

**Response:**
```json
{
  "faces": [
    {
      "bbox": [120, 85, 180, 220],
      "detection_confidence": 0.95,
      "identity": "John Doe",
      "match_score": 0.87
    },
    {
      "bbox": [400, 120, 160, 200],
      "detection_confidence": 0.92,
      "identity": "Unknown",
      "match_score": 0.0
    }
  ],
  "count": 2,
  "inference_time_ms": 125.8
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `faces` | array | List of recognized faces |
| `faces[].bbox` | array | Bounding box [x, y, w, h] |
| `faces[].detection_confidence` | float | Detection confidence |
| `faces[].identity` | string | Matched identity name or "Unknown" |
| `faces[].match_score` | float | Similarity score (0.0-1.0) |
| `count` | int | Number of faces |
| `inference_time_ms` | float | Total processing time |

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid image
- `503 Service Unavailable` - Database not enabled
- `500 Internal Server Error` - Recognition failure

---

### Add Identity

Add a new identity to the database with face embedding.

**Endpoint:** `POST /v1/database/add`

**Request Body:**
```json
{
  "name": "John Doe",
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "bbox": [120, 85, 180, 220]
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Identity name (unique) |
| `image` | string | Yes | Base64-encoded face image |
| `bbox` | array | No | Face bbox. Auto-detected if omitted. |

**Response:**
```json
{
  "message": "Identity 'John Doe' added successfully",
  "name": "John Doe"
}
```

**Status Codes:**
- `200 OK` - Identity added
- `400 Bad Request` - Missing name or no face detected
- `500 Internal Server Error` - Database error
- `503 Service Unavailable` - Database not enabled

---

### Remove Identity

Remove an identity and all its embeddings from the database.

**Endpoint:** `POST /v1/database/remove`

**Request Body:**
```json
{
  "name": "John Doe"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Identity name to remove |

**Response:**
```json
{
  "message": "Identity 'John Doe' removed successfully",
  "name": "John Doe"
}
```

**Status Codes:**
- `200 OK` - Identity removed
- `404 Not Found` - Identity not found
- `400 Bad Request` - Missing name
- `503 Service Unavailable` - Database not enabled

---

### List Identities

List all identities in the database.

**Endpoint:** `GET /v1/database/list`

**Response:**
```json
{
  "identities": [
    {
      "name": "John Doe",
      "embedding_count": 3,
      "created_at": "2026-01-15 10:30:45"
    },
    {
      "name": "Jane Smith",
      "embedding_count": 5,
      "created_at": "2026-01-20 14:22:10"
    }
  ],
  "count": 2
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `identities` | array | List of identities |
| `identities[].name` | string | Identity name |
| `identities[].embedding_count` | int | Number of stored embeddings |
| `identities[].created_at` | string | Creation timestamp |
| `count` | int | Total number of identities |

**Status Codes:**
- `200 OK` - Success
- `503 Service Unavailable` - Database not enabled

---

## Error Responses

All error responses follow this format:

```json
{
  "error": "Description of the error"
}
```

**Common Error Codes:**
- `400 Bad Request` - Invalid input (missing fields, malformed data)
- `404 Not Found` - Endpoint or resource not found
- `500 Internal Server Error` - Inference or processing failure
- `503 Service Unavailable` - Database or model not available

---

## Image Format

Images must be provided as base64-encoded strings with optional data URI prefix:

**With data URI (recommended):**
```
data:image/jpeg;base64,/9j/4AAQSkZJRg...
```

**Without prefix:**
```
/9j/4AAQSkZJRg...
```

**Supported formats:** JPEG, PNG, BMP, WebP

**Recommended:** JPEG for smaller payload size

---

## Bounding Box Format

Bounding boxes use `[x, y, width, height]` format:
- `x`: Left edge (pixels from left)
- `y`: Top edge (pixels from top)
- `width`: Box width (pixels)
- `height`: Box height (pixels)

---

## Embedding Format

Face embeddings are 512-dimensional float arrays normalized to unit length (L2 norm = 1.0).

**Example:**
```json
"embedding": [0.1234, -0.5678, 0.9012, ...]
```

**Length:** Always 512 elements  
**Type:** float32  
**Range:** Typically -1.0 to 1.0

---

## Performance Notes

- **Detection:** ~30-50ms per image
- **Embedding:** ~20-40ms per face
- **Recognition:** ~50-150ms per image (depends on database size)
- **Concurrent requests:** Supported with queue (max 10 by default)

---

## Example cURL Commands

### Detect faces
```bash
curl -X POST http://localhost:5002/v1/detect \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "image": "$(base64 -w0 photo.jpg | sed 's/^/data:image\/jpeg;base64,/')"
}
EOF
```

### Add identity
```bash
curl -X POST http://localhost:5002/v1/database/add \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "name": "John Doe",
  "image": "$(base64 -w0 john_doe.jpg | sed 's/^/data:image\/jpeg;base64,/')"
}
EOF
```

### Recognize faces
```bash
curl -X POST http://localhost:5002/v1/recognize \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "image": "$(base64 -w0 group_photo.jpg | sed 's/^/data:image\/jpeg;base64,/')",
  "threshold": 0.6
}
EOF
```

---

## Python Client Example

```python
import base64
import requests

API_URL = "http://localhost:5002"

def encode_image(path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/jpeg;base64,{b64}"

# Add identity
response = requests.post(
    f"{API_URL}/v1/database/add",
    json={
        "name": "John Doe",
        "image": encode_image("john_doe.jpg")
    }
)
print(response.json())

# Recognize faces
response = requests.post(
    f"{API_URL}/v1/recognize",
    json={
        "image": encode_image("group_photo.jpg"),
        "threshold": 0.6
    }
)
print(response.json())
```

---

## Rate Limiting

No rate limiting currently implemented. Consider using a reverse proxy (nginx) for production deployments.

---

## API Versioning

Current version: `v1`

Endpoints are versioned with `/v1/` prefix. Future breaking changes will use `/v2/`, etc.
