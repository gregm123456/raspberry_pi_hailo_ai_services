# Hailo-10H OCR API Specification

Base URL: `http://localhost:11436`

This service exposes a REST API for NPU-accelerated OCR using Hailo-10H, supporting text detection, recognition, and multi-language support.

## Common Request Parameters

### Images
Images can be provided via:
- **Base64 Data URI:** `"data:image/jpeg;base64,/9j/4AAQSk..."`
- **Local File:** `"file:///path/to/document.jpg"`

Supported formats: JPEG, PNG, BMP

- **Server preprocessing:** Images are resized with padding (letterbox) to the model input size on the server (preserves aspect ratio). Clients should send the original image (base64 or file); do not pre-resize or stretch images — the server handles aspect-ratio-preserving resizing and maps detection boxes back to the original image coordinates.

### Language Codes
- `en` — English (default)
- `zh` — Chinese (Simplified)

---

## GET /health
Health check endpoint. Returns service status and Hailo NPU usage.

**Response (200 OK):**
```json
{
  "status": "ok",
  "models_loaded": true,
  "languages_supported": ["en", "zh"],
  "memory_usage_mb": 1450,
  "uptime_seconds": 7200,
  "hailo_device": "/dev/hailo0"
}
```

---

## GET /health/ready
Readiness probe.

**Response (200 OK):** Service is ready.
```json
{"ready": true}
```

**Response (503 Service Unavailable):** Service is loading models.
```json
{"ready": false, "reason": "models_loading"}
```

---

## GET /models
Lists available HEF models on the NPU.

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "detection",
      "name": "ocr_det.hef",
      "type": "detection",
      "status": "loaded"
    },
    {
      "id": "recognition_en",
      "name": "ocr.hef",
      "type": "recognition",
      "language": "en",
      "status": "loaded"
    }
  ],
  "object": "list"
}
```

---

## POST /v1/ocr/extract
Extract text from an image using NPU-accelerated models.

**Request:**
```json
{
  "image": "data:image/jpeg;base64,...",
  "languages": ["en"]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "text": "Extracted text here",
  "regions": [
    {
      "text": "Extracted",
      "confidence": 0.95,
      "bbox": [[10, 20], [100, 20], [100, 50], [10, 50]],
      "type": "text"
    }
  ],
  "performance": {
    "detection_time_ms": 150,
    "recognition_time_ms": 200,
    "total_time_ms": 350
  },
  "hailo_info": {
    "device": "/dev/hailo0",
    "detection_model": "ocr_det.hef",
    "recognition_model": "ocr.hef"
  }
}
```

---

## Error Responses

- `400 Bad Request` — Invalid payload or image format.
- `503 Service Unavailable` — Models still loading.

**Error Response Format:**
```json
{
  "success": false,
  "error": "Failed to load image"
}
```

---

## Troubleshooting

- If thin fonts or low-contrast text are missed, try providing a higher-resolution image or improving contrast (e.g., increase brightness/contrast before sending).
- Detection uses DBNet with an adaptive binarization threshold around `0.3`; very light text or extreme aspect ratios may require higher-resolution input for reliable detection.
- If you see misrecognized characters (e.g., `lmage` vs `Image`), that is a recognition artifact — consider post-processing corrections or using a language-specific recognition HEF.

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | 3–5 images/second |
| **Latency** | 200–500 ms per image |
| **Batch Size (Rec)**| 8 (Accumulates regions for NPU efficiency) |
| **Memory (loaded)** | ~1.5 - 2.0 GB |
