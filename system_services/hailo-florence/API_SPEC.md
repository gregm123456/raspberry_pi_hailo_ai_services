# hailo-florence API Specification

**Version:** 1.0.0  
**Base URL:** `http://localhost:8082`  
**Protocol:** REST over HTTP  
**Content-Type:** `application/json`

---

## Endpoints

### 1. Generate Caption

Generate a natural language description of an image.

**Endpoint:** `POST /v1/caption`

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "max_length": 100,
  "min_length": 10,
  "temperature": 0.7
}
```

**Request Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image` | string | Yes | - | Base64-encoded image with data URI prefix |
| `max_length` | integer | No | 100 | Maximum caption length (tokens) |
| `min_length` | integer | No | 10 | Minimum caption length (tokens) |
| `temperature` | float | No | 0.7 | Sampling temperature (0.0-1.0) |

**Response (200 OK):**
```json
{
  "caption": "A person wearing a red shirt and blue jeans standing in front of a brick building while looking at their phone",
  "inference_time_ms": 750,
  "model": "florence-2",
  "token_count": 23
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `caption` | string | Generated natural language description |
| `inference_time_ms` | integer | Inference latency in milliseconds |
| `model` | string | Model identifier |
| `token_count` | integer | Number of tokens in generated caption |

**Error Responses:**

```json
// 400 Bad Request - Invalid image format
{
  "error": "invalid_image_format",
  "message": "Image must be base64-encoded JPEG or PNG",
  "status": 400
}

// 413 Payload Too Large - Image exceeds size limit
{
  "error": "image_too_large",
  "message": "Image size exceeds 10MB limit",
  "status": 413
}

// 422 Unprocessable Entity - Invalid parameters
{
  "error": "invalid_parameters",
  "message": "max_length must be between 10 and 200",
  "status": 422
}

// 500 Internal Server Error - Model inference failure
{
  "error": "inference_failed",
  "message": "Model inference encountered an error",
  "status": 500
}

// 503 Service Unavailable - Model not loaded
{
  "error": "model_not_ready",
  "message": "Florence-2 model is still loading, please retry",
  "status": 503
}
```

**Example Usage:**

```bash
# Basic caption generation
curl -X POST http://localhost:8082/v1/caption \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,'$(base64 -w0 image.jpg)'"
  }'

# With custom parameters
curl -X POST http://localhost:8082/v1/caption \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,'$(base64 -w0 image.jpg)'",
    "max_length": 150,
    "min_length": 30,
    "temperature": 0.5
  }'
```

**Python Example:**

```python
import base64
import requests

def caption_image(image_path, max_length=100):
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    response = requests.post(
        "http://localhost:8082/v1/caption",
        json={
            "image": f"data:image/jpeg;base64,{image_b64}",
            "max_length": max_length
        }
    )
    
    if response.status_code == 200:
        return response.json()["caption"]
    else:
        raise Exception(f"API error: {response.json()['message']}")

# Usage
caption = caption_image("photo.jpg", max_length=150)
print(caption)
```

---

### 2. Health Check

Check service health and model status.

**Endpoint:** `GET /health`

**Response (200 OK):**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "uptime_seconds": 3600,
  "version": "1.0.0",
  "hailo_device": "connected"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Overall service status: `healthy`, `degraded`, `unhealthy` |
| `model_loaded` | boolean | Whether Florence-2 model is loaded and ready |
| `uptime_seconds` | integer | Service uptime in seconds |
| `version` | string | Service version |
| `hailo_device` | string | Hailo device status: `connected`, `disconnected` |

**Error Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "model_loaded": false,
  "error": "Hailo device not found"
}
```

**Example Usage:**

```bash
curl http://localhost:8082/health
```

---

### 3. Service Metrics

Retrieve service performance metrics.

**Endpoint:** `GET /metrics`

**Response (200 OK):**
```json
{
  "requests_total": 1523,
  "requests_succeeded": 1498,
  "requests_failed": 25,
  "average_inference_time_ms": 782,
  "p50_inference_time_ms": 750,
  "p95_inference_time_ms": 920,
  "p99_inference_time_ms": 1050,
  "memory_usage_mb": 3200,
  "model_cache_hit_rate": 1.0,
  "uptime_seconds": 86400
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `requests_total` | integer | Total requests received |
| `requests_succeeded` | integer | Successfully processed requests |
| `requests_failed` | integer | Failed requests |
| `average_inference_time_ms` | float | Mean inference latency |
| `p50_inference_time_ms` | float | Median inference latency |
| `p95_inference_time_ms` | float | 95th percentile latency |
| `p99_inference_time_ms` | float | 99th percentile latency |
| `memory_usage_mb` | integer | Current memory usage (MB) |
| `model_cache_hit_rate` | float | Model cache efficiency (0.0-1.0) |
| `uptime_seconds` | integer | Service uptime in seconds |

**Example Usage:**

```bash
curl http://localhost:8082/metrics
```

---

## Rate Limiting

No rate limiting is enforced by default. However, due to the inference latency (~500-1000ms per request), the effective throughput is limited to approximately 1-2 requests per second.

**Recommendation:** For production deployments, implement client-side rate limiting or deploy a reverse proxy (e.g., nginx) with request queuing.

---

## Image Format Requirements

### Supported Formats
- JPEG (.jpg, .jpeg)
- PNG (.png)

### Size Limits
- **Maximum file size:** 10 MB
- **Maximum dimensions:** 4096 x 4096 pixels
- **Minimum dimensions:** 224 x 224 pixels

### Encoding Requirements
- Images must be base64-encoded
- Data URI prefix required: `data:image/jpeg;base64,` or `data:image/png;base64,`
- No line breaks in base64 string

### Image Preprocessing
Images are automatically:
1. Resized to model input size (384 x 384 for Florence-2)
2. Normalized to [0, 1] range
3. Converted to RGB (if grayscale or RGBA)

---

## Error Handling

All errors follow a consistent format:

```json
{
  "error": "error_code",
  "message": "Human-readable error description",
  "status": 400
}
```

### Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `invalid_image_format` | 400 | Image format not supported or invalid base64 |
| `image_too_large` | 413 | Image exceeds size limits |
| `invalid_parameters` | 422 | Request parameters out of valid range |
| `inference_failed` | 500 | Model inference encountered an error |
| `model_not_ready` | 503 | Model still loading or not available |
| `device_error` | 503 | Hailo device not accessible |

---

## Authentication

**Current Version:** No authentication required (localhost-only deployment).

**Future Enhancement:** For network-exposed deployments, consider adding:
- API key authentication (`X-API-Key` header)
- JWT-based authentication
- Rate limiting per API key

---

## Versioning

API version is specified in the URL path: `/v1/caption`

**Version Policy:**
- Major version changes (`/v1/` → `/v2/`) indicate breaking changes
- Minor updates maintain backward compatibility
- Current version: `v1`

---

## Examples

### Batch Processing Script

```python
#!/usr/bin/env python3
import base64
import requests
from pathlib import Path
import json

API_URL = "http://localhost:8082/v1/caption"

def batch_caption(image_dir, output_file):
    results = []
    
    for image_path in Path(image_dir).glob("*.jpg"):
        print(f"Processing {image_path.name}...")
        
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode('utf-8')
        
        response = requests.post(
            API_URL,
            json={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "max_length": 100
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            results.append({
                "filename": image_path.name,
                "caption": result["caption"],
                "inference_time_ms": result["inference_time_ms"]
            })
        else:
            print(f"  Error: {response.json()['message']}")
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Saved {len(results)} captions to {output_file}")

if __name__ == "__main__":
    batch_caption("images/", "captions.json")
```

### Integration with Flask App

```python
from flask import Flask, request, jsonify
import base64
import requests

app = Flask(__name__)
FLORENCE_API = "http://localhost:8082/v1/caption"

@app.route('/describe', methods=['POST'])
def describe_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    
    image_file = request.files['image']
    image_b64 = base64.b64encode(image_file.read()).decode('utf-8')
    
    response = requests.post(
        FLORENCE_API,
        json={
            "image": f"data:image/jpeg;base64,{image_b64}",
            "max_length": 150
        }
    )
    
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(port=5000)
```

---

## Performance Considerations

### Latency Expectations
- **Single image:** 500-1000ms
- **Batch processing:** Queue requests sequentially
- **Concurrent requests:** Handled in FIFO order (no parallel processing)

### Optimization Tips
1. **Image size:** Smaller images (< 2MB) reduce preprocessing time
2. **max_length:** Shorter captions generate faster
3. **Batch mode:** Process multiple images sequentially to amortize startup costs
4. **Model caching:** First request after service start will be slower (~1-2s)

### Resource Usage
- **VRAM:** 2-3 GB (persistent model loading)
- **CPU:** Moderate during inference (encoder on CPU, decoder on Hailo)
- **Memory:** ~3.5 GB total (including model + buffers)

---

**Last Updated:** January 31, 2026  
**API Version:** v1  
**Service Version:** 1.0.0
