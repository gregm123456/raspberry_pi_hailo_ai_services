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

- `temperature` (float) — Sampling temperature (0.0 = deterministic, 1.0 = normal, 2.0 = very random; default: 0.7)
- `max_tokens` (int) — Maximum tokens to generate (default: 200)
- `top_p` (float) — Nucleus sampling threshold (0.0–1.0; default: 0.9)
- `seed` (int) — Random seed for reproducible outputs

---

## GET /health

Health check endpoint. Returns service status and readiness.

**Response (200 OK):**
```json
{
  "status": "ok",
  "model": "qwen2-vl-2b-instruct",
  "model_loaded": true,
  "memory_usage_mb": 2842,
  "uptime_seconds": 3600
}
```

**Example:**
```bash
curl http://localhost:11435/health
```

---

## GET /health/ready

Readiness probe (used by systemd or orchestration).

**Response (200 OK):** Service is ready to accept requests.
```json
{"ready": true}
```

**Response (503 Service Unavailable):** Service is loading or unavailable.
```json
{"ready": false, "reason": "model_loading"}
```

**Example:**
```bash
curl http://localhost:11435/health/ready
```

---

## GET /v1/models

Lists available vision models.

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "qwen2-vl-2b-instruct",
      "object": "model",
      "created": 1706745600,
      "owned_by": "hailo"
    }
  ],
  "object": "list"
}
```

**Example:**
```bash
curl http://localhost:11435/v1/models
```

---

## POST /v1/chat/completions

Run vision inference with chat-based interface. Accepts images and text prompts for multimodal understanding.

**Request:**
```json
{
  "model": "qwen2-vl-2b-instruct",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image",
          "image_url": {
            "url": "data:image/jpeg;base64,/9j/4AAQSk..."
          }
        },
        {
          "type": "text",
          "text": "Describe what you see in this image. Who is in it, what are they wearing, and what are they doing?"
        }
      ]
    }
  ],
  "temperature": 0.7,
  "max_tokens": 200,
  "top_p": 0.9,
  "stream": false
}
```

**Parameters:**
- `model` (required) — Must be `"qwen2-vl-2b-instruct"`
- `messages` (required) — Array of message objects:
  - `role` (required) — `"system"`, `"user"`, or `"assistant"`
  - `content` (required) — String (text) or array of content blocks:
    - `type: "text"` — Text message
    - `type: "image"` — Image with `image_url` object containing `url` (data URI, HTTP URL, or file path)
- `temperature` (optional, default: 0.7) — Sampling temperature (0.0–2.0)
- `max_tokens` (optional, default: 200) — Maximum tokens to generate
- `top_p` (optional, default: 0.9) — Nucleus sampling (0.0–1.0)
- `seed` (optional) — Random seed for reproducibility
- `stream` (optional, default: false) — Stream response tokens

**Response (200 OK):**
```json
{
  "id": "chatcmpl-8a5c2d1f",
  "object": "chat.completion",
  "created": 1706745600,
  "model": "qwen2-vl-2b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "In this image, I can see a person wearing a red shirt and blue jeans standing in front of a brick building. They appear to be looking at their phone. The building has a classic brick facade, and the setting looks like an urban street."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 256,
    "completion_tokens": 62,
    "total_tokens": 318
  },
  "performance": {
    "inference_time_ms": 850,
    "load_time_ms": 120
  }
}
```

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
