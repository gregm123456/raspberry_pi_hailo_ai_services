# Hailo Vision API Specification

Base URL: `http://localhost:11435`

This service exposes a chat-based Vision API compatible with OpenAI's Chat Completion API, supporting multimodal image+text prompts for visual question-answering and image analysis.

## Common Request Parameters

### Images

Images can be provided via:
- **Base64 Data URI:** `"data:image/jpeg;base64,/9j/4AAQSk..."`
- **URL:** `"https://example.com/image.jpg"` (must be network-accessible)
- **Local File:** `"file:///path/to/image.jpg"` (read from service host filesystem)

Supported formats: JPEG, PNG, WebP

### Generation Options

- `temperature` (float) — Sampling temperature (0.0 = deterministic, 1.0 = normal; default: 0.7)
- `max_tokens` (int) — Maximum tokens to generate (default: 200)
- `top_p` (float) — Nucleus sampling threshold (0.0–1.0; default: 0.9)

---

## GET /health

Returns service status, model loading state, and uptime.

**Response (200 OK):**
```json
{
  "status": "ok",
  "model": "qwen2-vl-2b-instruct",
  "model_loaded": true,
  "uptime_seconds": 3600,
  "hailo_device": "/dev/hailo0"
}
```

---

## POST /v1/chat/completions

Standard OpenAI-compatible endpoint for VLM inference.

**Request Structure:**
- `model`: (string) Must be `qwen2-vl-2b-instruct`.
- `messages`: (array) List of message objects.
  - `content`: (string or array) If array, can contain blocks of `type: "text"` or `type: "image_url"`.

**Special Features:**
- **Bundled Base64**: In addition to standard `image_url: {"url": "data:..."}`, we support `type: "image"` with a direct `image` or `data` field containing the raw base64 string.
- **Performance Metadata**: The response includes a `performance` object with `inference_time_ms`.

---

## Deployment Configuration

The service is managed via `/etc/hailo/hailo-vision.yaml`.

```yaml
server:
  host: 0.0.0.0
  port: 11435

model:
  name: "qwen2-vl-2b-instruct"
```

## Security & Isolation
- **User**: Runs as `hailo-vision` system user.
- **Isolaton**: Vendored code in `/opt/hailo-vision/vendor`.
- **Paths**: Models stored in `/var/lib/hailo-vision/resources`.


**Streaming Response (stream=true):**
```
data: {"choices":[{"delta":{"content":"In"}}]}
data: {"choices":[{"delta":{"content":" this"}}]}
...
data: [DONE]
```

**Example (Simple Description):**
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image",
            "image_url": {
              "url": "data:image/jpeg;base64,/9j/4AAQSkZJ..."
            }
          },
          {
            "type": "text",
            "text": "Describe this image in one sentence."
          }
        ]
      }
    ],
    "temperature": 0.7,
    "max_tokens": 100,
    "stream": false
  }'
```

**Example (Safety Classification):**
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image",
            "image_url": {
              "url": "data:image/jpeg;base64,/9j/4AAQSkZJ..."
            }
          },
          {
            "type": "text",
            "text": "Is this image safe for work? Answer with one word: SAFE or UNSAFE."
          }
        ]
      }
    ],
    "temperature": 0.0,
    "max_tokens": 10
  }'
```

**Example (Multi-Turn Conversation with Image):**
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "image",
            "image_url": {
              "url": "data:image/jpeg;base64,/9j/4AAQSkZJ..."
            }
          },
          {
            "type": "text",
            "text": "Describe this image."
          }
        ]
      },
      {
        "role": "assistant",
        "content": "This image shows a red car parked on a street..."
      },
      {
        "role": "user",
        "content": "What color is the car?"
      }
    ],
    "stream": false
  }'
```

---

## POST /v1/vision/analyze

Direct endpoint for batch image analysis (alternative to `/v1/chat/completions`).

**Request:**
```json
{
  "images": [
    "data:image/jpeg;base64,/9j/4AAQSkZJ...",
    "data:image/png;base64,iVBORw0KGgo..."
  ],
  "prompt": "For each image, describe the main objects and their colors.",
  "temperature": 0.7,
  "max_tokens": 150
}
```

**Parameters:**
- `images` (required) — Array of image URIs (base64 data, HTTP URLs, or file paths)
- `prompt` (required) — Analysis prompt
- `temperature` (optional, default: 0.7) — Sampling temperature
- `max_tokens` (optional, default: 150) — Maximum tokens per image
- `return_individual_results` (optional, default: false) — Return separate results for each image

**Response (200 OK):**
```json
{
  "results": [
    {
      "image_url": "data:image/jpeg;base64,...",
      "analysis": "This image contains a red bicycle leaning against a wooden bench..."
    },
    {
      "image_url": "data:image/png;base64,...",
      "analysis": "A digital display showing weather information..."
    }
  ],
  "total_inference_time_ms": 1650
}
```

**Example:**
```bash
curl -X POST http://localhost:11435/v1/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "images": [
      "data:image/jpeg;base64,/9j/4AAQSkZJ..."
    ],
    "prompt": "Is anyone wearing safety equipment in this image?",
    "temperature": 0.0,
    "max_tokens": 50
  }'
```

---

## Error Responses

Standard HTTP status codes are used:

- `400 Bad Request` — Invalid payload or missing required parameters
- `401 Unauthorized` — Authentication error (if auth is enabled)
- `404 Not Found` — Model not found or invalid endpoint
- `413 Payload Too Large` — Image payload exceeds size limit (~10 MB)
- `500 Internal Server Error` — Model inference failure
- `503 Service Unavailable` — Service initializing or device unavailable

**Error Response Format:**
```json
{
  "error": {
    "message": "Image resolution exceeds maximum (9216x4096)",
    "type": "invalid_request_error",
    "code": "invalid_image_resolution"
  }
}
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | ~2–5 images/second |
| **Latency (avg)** | 200–600 ms (first load 1–2s) |
| **Max Image Size** | 8 MP (3840×2160) |
| **Max Tokens** | 512 |
| **Memory (loaded)** | ~2–4 GB VRAM |

---

## OpenAI Compatibility

This API implements the OpenAI Vision API standard:
- Chat Completions format with multimodal content
- Compatible with `openai-python` library:
  ```python
  from openai import OpenAI
  
  client = OpenAI(base_url="http://localhost:11435/v1", api_key="not-needed")
  response = client.chat.completions.create(
    model="qwen2-vl-2b-instruct",
    messages=[
      {
        "role": "user",
        "content": [
          {"type": "image", "image_url": {"url": "data:image/jpeg;base64,..."}},
          {"type": "text", "text": "Describe this image."}
        ]
      }
    ]
  )
  ```
