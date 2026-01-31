# Hailo OCR API Specification

Base URL: `http://localhost:11436`

This service exposes a REST API for Optical Character Recognition (OCR) using PaddleOCR, supporting text detection, recognition, batch processing, and result caching.

## Common Request Parameters

### Images

Images can be provided via:
- **Base64 Data URI:** `"data:image/jpeg;base64,/9j/4AAQSk..."`
- **URL:** `"https://example.com/document.jpg"` (must be network-accessible)
- **Local File:** `"file:///path/to/document.jpg"` (read from service host filesystem)

Supported formats: JPEG, PNG, WebP, BMP

### Language Codes

- `en` — English (default)
- `ch_sim` — Simplified Chinese
- `ch_tra` — Traditional Chinese
- `fr` — French
- `de` — German
- `es` — Spanish
- `ja` — Japanese
- `ko` — Korean
- [Additional language codes supported by PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.7/doc/doc_en/multi_languages_en.md)

---

## GET /health

Health check endpoint. Returns service status and resource usage.

**Response (200 OK):**
```json
{
  "status": "ok",
  "models_loaded": true,
  "detection_model": "ch_PP-OCRv3_det_infer",
  "recognition_model": "ch_PP-OCRv3_rec_infer",
  "memory_usage_mb": 1450,
  "cache_size_mb": 85,
  "uptime_seconds": 7200
}
```

**Example:**
```bash
curl http://localhost:11436/health
```

---

## GET /health/ready

Readiness probe (used by systemd or orchestration).

**Response (200 OK):** Service is ready to accept requests.
```json
{"ready": true}
```

**Response (503 Service Unavailable):** Service is loading models or unavailable.
```json
{"ready": false, "reason": "models_loading"}
```

**Example:**
```bash
curl http://localhost:11436/health/ready
```

---

## GET /models

Lists available OCR language models.

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "en",
      "name": "English",
      "detection_model": "ch_PP-OCRv3_det_infer",
      "recognition_model": "en_PP-OCRv3_rec_infer",
      "status": "loaded"
    },
    {
      "id": "ch_sim",
      "name": "Simplified Chinese",
      "detection_model": "ch_PP-OCRv3_det_infer",
      "recognition_model": "ch_PP-OCRv3_rec_infer",
      "status": "available"
    }
  ],
  "object": "list"
}
```

**Example:**
```bash
curl http://localhost:11436/models
```

---

## POST /v1/ocr/extract

Extract text from a single image using OCR.

**Request:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSk...",
  "languages": ["en"],
  "enable_recognition": true,
  "det_threshold": 0.3,
  "rec_threshold": 0.5,
  "return_confidence": true,
  "cache_result": true
}
```

**Parameters:**
- `image` (required) — Image URI (base64 data, HTTP URL, or file path)
- `languages` (optional, default: `["en"]`) — Array of language codes to detect
- `enable_recognition` (optional, default: `true`) — Perform character recognition
- `det_threshold` (optional, default: 0.3) — Detection confidence threshold (0.0–1.0)
- `rec_threshold` (optional, default: 0.5) — Recognition confidence threshold (0.0–1.0)
- `return_confidence` (optional, default: `true`) — Include confidence scores in response
- `cache_result` (optional, default: `false`) — Store result in memory cache
- `request_id` (optional) — Custom request identifier for logging

**Response (200 OK):**
```json
{
  "success": true,
  "request_id": "ocr-abc123",
  "text": "Sample text extracted from image",
  "languages_detected": ["en"],
  "regions": [
    {
      "text": "Sample",
      "confidence": 0.95,
      "bbox": [[10, 20], [100, 20], [100, 50], [10, 50]],
      "type": "text",
      "language": "en"
    },
    {
      "text": "text",
      "confidence": 0.92,
      "bbox": [[110, 20], [170, 20], [170, 50], [110, 50]],
      "type": "text",
      "language": "en"
    }
  ],
  "statistics": {
    "total_regions": 2,
    "average_confidence": 0.935,
    "image_size": [1920, 1080],
    "image_format": "jpeg"
  },
  "performance": {
    "model_load_time_ms": 2500,
    "detection_time_ms": 150,
    "recognition_time_ms": 200,
    "total_time_ms": 2850
  },
  "cached": false
}
```

**Example (Basic):**
```bash
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJ...",
    "languages": ["en"]
  }'
```

**Example (English Document):**
```bash
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "https://example.com/invoice.jpg",
    "languages": ["en"],
    "enable_recognition": true,
    "cache_result": true
  }'
```

**Example (Multi-Language):**
```bash
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJ...",
    "languages": ["en", "ch_sim"],
    "det_threshold": 0.4,
    "rec_threshold": 0.6
  }'
```

---

## POST /v1/ocr/batch

Process multiple images in batch mode.

**Request:**
```json
{
  "images": [
    "data:image/jpeg;base64,/9j/4AAQSkZJ...",
    "https://example.com/page2.jpg"
  ],
  "languages": ["en"],
  "enable_recognition": true,
  "cache_results": false,
  "parallel_limit": 2
}
```

**Parameters:**
- `images` (required) — Array of image URIs
- `languages` (optional, default: `["en"]`) — Languages to detect across all images
- `enable_recognition` (optional, default: `true`) — Perform recognition on all images
- `cache_results` (optional, default: `false`) — Cache each result individually
- `parallel_limit` (optional, default: 1) — Number of images to process in parallel (CPU-bound, use 1-2)
- `skip_errors` (optional, default: `false`) — Continue processing on individual image failures

**Response (200 OK):**
```json
{
  "success": true,
  "batch_id": "batch-xyz789",
  "images_processed": 2,
  "results": [
    {
      "image_url": "data:image/jpeg;base64,/9j/...",
      "status": "success",
      "text": "Page 1 text",
      "regions": [...],
      "performance": {
        "detection_time_ms": 150,
        "recognition_time_ms": 200,
        "total_time_ms": 350
      }
    },
    {
      "image_url": "https://example.com/page2.jpg",
      "status": "success",
      "text": "Page 2 text",
      "regions": [...],
      "performance": {
        "detection_time_ms": 140,
        "recognition_time_ms": 190,
        "total_time_ms": 330
      }
    }
  ],
  "batch_statistics": {
    "total_time_ms": 680,
    "average_image_time_ms": 340,
    "total_regions": 24,
    "average_confidence": 0.91
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:11436/v1/ocr/batch \
  -H "Content-Type: application/json" \
  -d '{
    "images": [
      "data:image/jpeg;base64,/9j/4AAQSkZJ...",
      "file:///tmp/page2.png"
    ],
    "languages": ["en"],
    "parallel_limit": 2
  }'
```

---

## POST /v1/ocr/analyze

Advanced OCR analysis with layout detection and structured output.

**Request:**
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQSk...",
  "languages": ["en"],
  "detect_layout": true,
  "return_structure": true,
  "analysis_options": {
    "extract_tables": false,
    "detect_headings": true,
    "segment_paragraphs": true
  }
}
```

**Parameters:**
- `image` (required) — Image URI
- `languages` (optional, default: `["en"]`) — Language codes
- `detect_layout` (optional, default: `false`) — Detect document layout
- `return_structure` (optional, default: `false`) — Return structured document tree
- `analysis_options` (optional) — Analysis configuration:
  - `extract_tables` (bool) — Detect and extract table data
  - `detect_headings` (bool) — Identify heading hierarchy
  - `segment_paragraphs` (bool) — Group text into paragraphs

**Response (200 OK):**
```json
{
  "success": true,
  "text": "Document text",
  "regions": [...],
  "layout": {
    "type": "document",
    "page_width": 1920,
    "page_height": 1080,
    "elements": [
      {
        "type": "heading",
        "level": 1,
        "text": "Title",
        "bbox": [[50, 50], [500, 50], [500, 100], [50, 100]]
      },
      {
        "type": "paragraph",
        "text": "Body text",
        "bbox": [[50, 120], [1870, 120], [1870, 400], [50, 400]]
      }
    ]
  },
  "performance": {
    "detection_time_ms": 150,
    "recognition_time_ms": 200,
    "layout_analysis_time_ms": 100,
    "total_time_ms": 450
  }
}
```

---

## DELETE /cache

Clear the in-memory result cache.

**Response (200 OK):**
```json
{
  "success": true,
  "cache_cleared": true,
  "items_removed": 42,
  "freed_memory_mb": 85
}
```

**Example:**
```bash
curl -X DELETE http://localhost:11436/cache
```

---

## GET /cache/stats

Get cache statistics.

**Response (200 OK):**
```json
{
  "enabled": true,
  "items_cached": 42,
  "memory_used_mb": 85,
  "memory_limit_mb": 500,
  "ttl_seconds": 3600,
  "hits": 128,
  "misses": 256,
  "hit_rate": 0.33
}
```

**Example:**
```bash
curl http://localhost:11436/cache/stats
```

---

## Error Responses

Standard HTTP status codes are used:

- `400 Bad Request` — Invalid payload or missing required parameters
- `401 Unauthorized` — Authentication error (if auth is enabled)
- `404 Not Found` — Model not found or invalid endpoint
- `413 Payload Too Large` — Image payload exceeds size limit (~10 MB)
- `503 Service Unavailable` — Service initializing or models loading

**Error Response Format:**
```json
{
  "success": false,
  "error": {
    "message": "Image resolution 9216x4096 exceeds maximum (4096x4096)",
    "type": "invalid_image_error",
    "code": "image_too_large",
    "details": {
      "input_size": "9216x4096",
      "max_size": "4096x4096"
    }
  }
}
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | 2–5 images/second |
| **Throughput (parallel, 2x)** | 3–7 images/second |
| **Latency (avg, model loaded)** | 200–600 ms per image |
| **Latency (first call, model load)** | 2–3 seconds |
| **Max Image Size** | 4096×4096 pixels |
| **Memory (loaded)** | 1.5–2.5 GB VRAM |

---

## Rate Limiting & Quotas

This API is not rate-limited by default. If rate limiting is required, implement at the deployment layer (nginx, reverse proxy, etc.):

```nginx
limit_req_zone $binary_remote_addr zone=ocr_limit:10m rate=10r/s;
limit_req zone=ocr_limit burst=20 nodelay;
```

---

## Examples

### Extract text from document

```bash
# Read image and encode
IMAGE_DATA=$(base64 -w0 < document.jpg)

curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d "{
    \"image\": \"data:image/jpeg;base64,$IMAGE_DATA\",
    \"languages\": [\"en\"],
    \"cache_result\": true
  }"
```

### Batch process multiple documents

```bash
curl -X POST http://localhost:11436/v1/ocr/batch \
  -H "Content-Type: application/json" \
  -d '{
    "images": [
      "file:///documents/page1.jpg",
      "file:///documents/page2.jpg",
      "file:///documents/page3.jpg"
    ],
    "languages": ["en"],
    "parallel_limit": 2
  }' | jq '.results[].text'
```

### Clear cache and get stats

```bash
# Check cache before clear
curl http://localhost:11436/cache/stats

# Clear cache
curl -X DELETE http://localhost:11436/cache

# Verify cleared
curl http://localhost:11436/cache/stats
```

---

## Notes

- **Image Encoding:** Use base64 without newlines: `base64 -w0 < image.jpg`
- **Timeout:** Long requests (large images, slow networks) may timeout after 30s
- **Concurrency:** Service handles 1-2 concurrent OCR requests efficiently; queue additional requests
- **Languages:** Adding new languages requires downloading models (~500 MB each); updates config and restarts service
