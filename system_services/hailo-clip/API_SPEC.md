# Hailo CLIP Service - API Specification

REST API for zero-shot image classification using CLIP model on Hailo-10H.

## Base URL

```
http://localhost:5000
```

## Endpoints

### Health Check

**GET** `/health`

Check service status and model availability.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "hailo-clip",
  "model_loaded": true,
  "model": "clip-vit-b-32"
}
```

---

### Image Classification

**POST** `/v1/classify`

Classify an image against one or more text prompts using cosine similarity.
The service applies a scaled softmax (logit scale: 100) to ensure high confidence differentiation between prompts.

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "prompts": [
    "person wearing red shirt",
    "person wearing blue shirt",
    "person on bicycle",
    "person wearing helmet"
  ],
  "top_k": 3,
  "threshold": 0.0
}
```

**Parameters:**
- `image` (string, required): Base64-encoded image with optional data URI prefix
- `prompts` (array of strings, required): Text descriptions to match. CLIP performs significantly better with full descriptive sentences (e.g., "a photo of a person") than single keywords.
- `top_k` (integer, optional): Return top-k matches (default: 3, capped at prompts length)
- `threshold` (number, optional): Minimum similarity threshold (default: 0.0, range: [0.0, 1.0])

**Response (200 OK):**
```json
{
  "classifications": [
    {
      "text": "person wearing red shirt",
      "score": 0.999,
      "rank": 1
    },
    {
      "text": "person wearing helmet",
      "score": 0.001,
      "rank": 2
    },
    {
      "text": "person on bicycle",
      "score": 0.0,
      "rank": 3
    }
  ],
  "inference_time_ms": 145,
  "model": "clip-vit-b-32"
}
```

**Response Fields:**
- `classifications` (array): Ranked matches by similarity (0.0 to 1.0)
- `inference_time_ms` (number): Total inference latency in milliseconds
- `model` (string): CLIP model variant used

**Error Responses:**
- 400: Missing/invalid image or prompts
- 500: Model inference failed

---

### Image Embedding

**POST** `/v1/embed/image`

Get CLIP embedding vector for an image.

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
}
```

**Response (200 OK):**
```json
{
  "embedding": [0.123, -0.456, 0.789, ...],
  "dimension": 512,
  "model": "clip-vit-b-32"
}
```

**Response Fields:**
- `embedding` (array of floats): Normalized 512-dimensional vector
- `dimension` (integer): Embedding dimension
- `model` (string): Model used

---

### Text Embedding

**POST** `/v1/embed/text`

Get CLIP embedding vector for text.

**Request Body:**
```json
{
  "text": "person wearing red shirt"
}
```

**Response (200 OK):**
```json
{
  "embedding": [0.123, -0.456, 0.789, ...],
  "dimension": 512,
  "model": "clip-vit-b-32"
}
```

---

## Usage Examples

### cURL - Classification

```bash
# Prepare image (convert to base64)
IMAGE_B64=$(base64 -w0 < image.jpg)

# Classify
curl -X POST http://localhost:5000/v1/classify \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,${IMAGE_B64}\",
    \"prompts\": [
      \"a photo of a person with a smile\",
      \"a photo of a person with a frown\",
      \"a photo of a person with a neutral expression\"
    ],
    \"top_k\": 1
  }" | jq .
```

### Python - Classification

```python
import requests
import base64

# Read image and encode
with open("image.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

# Call API
response = requests.post(
    "http://localhost:5000/v1/classify",
    json={
        "image": f"data:image/jpeg;base64,{image_b64}",
        "prompts": [
            "a photo of a person with a smile",
            "a photo of a person with a frown",
            "a photo of a person with a neutral expression"
        ],
        "top_k": 1,
        "threshold": 0.3
    }
)

result = response.json()
print(f"Top match: {result['classifications'][0]}")
print(f"Inference time: {result['inference_time_ms']:.1f}ms")
```

### Get Embeddings

```bash
# Image embedding
curl -X POST http://localhost:5000/v1/embed/image \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"data:image/jpeg;base64,...\"}" | jq .

# Text embedding
curl -X POST http://localhost:5000/v1/embed/text \
  -H "Content-Type: application/json" \
  -d '{"text": "a photo of a person wearing red shirt"}' | jq .
```

---

## Error Handling

### 400 Bad Request

Missing or malformed request:
```json
{
  "error": "Missing or invalid 'prompts' array"
}
```

### 500 Internal Server Error

Model inference failure:
```json
{
  "error": "Failed to encode image"
}
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Throughput | ~30-50 fps |
| Image encoding latency | ~25-40ms |
| Text encoding latency | ~5-15ms |
| Model Memory (RAM/VRAM) | ~1-1.5 GB |
| Typical response time | 40-100ms (depending on prompt count) |

---

## Model Details

### CLIP ViT-B/32

- **Embedding dimension:** 512
- **Image input:** 224×224 RGB
- **Output:** Normalized L2 embeddings
- **Similarity metric:** Cosine similarity scaled by 100 via Softmax
- **Hardware:** Hailo-10H NPU (Raspberry Pi 5)

---

## Rate Limiting

No built-in rate limiting. Configure via reverse proxy if needed.

---

## Concurrency

- Default worker threads: 2 (configurable in `/etc/hailo/hailo-clip.yaml`)
- Thread-safe model inference with RLock
- Max queue size: 10 concurrent requests (configurable)
