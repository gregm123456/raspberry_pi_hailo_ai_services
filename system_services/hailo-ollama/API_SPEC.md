# Hailo Ollama API Specification

Base URL: `http://localhost:11434`

This service exposes the upstream `hailo-ollama` API. Endpoints and payloads mirror the Ollama API.

## Common Parameters

### keep_alive

Controls model lifecycle in memory (supported on `/api/chat`, `/api/generate`):

- **`-1`** — Keep model loaded indefinitely (persist until explicit unload)
- **`0`** — Unload model immediately after request completes
- **`<seconds>`** — Keep loaded for specified seconds (e.g., `300` = 5 minutes)
- **Not specified** — Default: 300 seconds (5 minutes)

**Example:**
```json
{"model": "qwen2:1.5b", "prompt": "Hello", "keep_alive": -1}
```

### options (Model Parameters)

Fine-tune generation behavior (supported on `/api/chat`, `/api/generate`):

- `temperature` (float) — Sampling temperature (0.0 = deterministic, 2.0 = very random)
- `seed` (int) — Random seed for reproducible outputs
- `top_k` (int) — Limit sampling to top K tokens
- `top_p` (float) — Nucleus sampling threshold (0.0-1.0)
- `frequency_penalty` (float) — Penalize frequently used tokens
- `num_predict` (int) — Maximum tokens to generate

**Example:**
```json
{
  "model": "qwen2:1.5b",
  "prompt": "Hello",
  "options": {
    "temperature": 0.7,
    "seed": 42,
    "top_k": 40,
    "top_p": 0.9
  }
}
```

---

## GET /api/version

Returns server version information.

**Response (200 OK):**
```json
{"version":"0.1.0"}
```

**Example:**
```bash
curl http://localhost:11434/api/version
```

## GET /api/tags

Lists available models with detailed metadata.

**Response (200 OK):**
```json
{
  "models": [
    {
      "name": "qwen2:1.5b",
      "model": "qwen2:1.5b",
      "size": 1234567890,
      "digest": "abc123...",
      "modified_at": "2026-01-31T10:00:00Z",
      "details": {
        "parent_model": "",
        "format": "hef",
        "family": "qwen2",
        "families": ["qwen2"],
        "parameter_size": "1.5B",
        "quantization_level": "int8"
      },
      "expires_at": "2026-01-31T10:15:00Z"
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:11434/api/tags
```

## GET /hailo/v1/list

Lists available models in a simplified format (model names only).

**Response (200 OK):**
```json
{
  "models": ["qwen2:1.5b", "llama3.2:3b", "qwen2.5-coder:1.5b"]
}
```

**Example:**
```bash
curl http://localhost:11434/hailo/v1/list
```

## GET /api/ps

Lists currently running/loaded models with expiration times.

**Response (200 OK):**
```json
{
  "models": [
    {
      "name": "qwen2:1.5b",
      "expires_at": "2026-01-31T10:15:00Z"
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:11434/api/ps
```

## POST /api/show

Shows detailed metadata about a specific model (license, stop tokens, parameters).

**Request:**
```json
{"model": "qwen2:1.5b"}
```

**Response (200 OK):**
```json
{
  "license": "MIT",
  "modelfile": "...",
  "parameters": "...",
  "template": "<chat_template>",
  "details": {
    "parent_model": "",
    "format": "hef",
    "family": "qwen2",
    "families": ["qwen2"],
    "parameter_size": "1.5B",
    "quantization_level": "int8"
  },
  "model_info": "...",
  "capabilities": ["chat", "generate"],
  "modified_at": "2026-01-31T10:00:00Z"
}
```

**Example:**
```bash
curl -X POST http://localhost:11434/api/show \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b"}'
```

## POST /api/pull

Downloads a model into the local cache.

**Request:**
```json
{
  "model": "qwen2:1.5b",
  "stream": true
}
```

**Parameters:**
- `model` (required) — Model name to download
- `stream` (optional, default: true) — Stream download progress

**Response (200 OK):** Streaming JSON progress updates.

**Example:**
```bash
curl -X POST http://localhost:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b","stream":true}'
```

**Note:** Currently returns HTTP 500 in hailo-ollama v0.5.1 (upstream limitation). Models can be installed manually via package manager.

## POST /api/chat

Runs chat inference.

**Request:**
```json
{
  "model": "qwen2:1.5b",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "keep_alive": -1,
  "format": "json",
  "tools": "[...]",
  "options": {
    "temperature": 0.7,
    "seed": 42,
    "top_k": 40,
    "top_p": 0.9,
    "frequency_penalty": 0.0,
    "num_predict": 128
  }
}
```

**Parameters:**
- `model` (required) — Model name
- `messages` (required) — Array of message objects with `role` and `content`
- `stream` (optional, default: true) — Stream response tokens
- `keep_alive` (optional, default: 300) — Keep model loaded for N seconds; `-1` = indefinite, `0` = unload immediately
- `format` (optional) — Response format (e.g., `"json"`)
- `tools` (optional) — JSON string defining function calling tools
- `options` (optional) — Model parameters:
  - `temperature` — Randomness (0.0-2.0, default ~0.7)
  - `seed` — Random seed for reproducibility
  - `top_k` — Top-K sampling limit
  - `top_p` — Nucleus sampling threshold
  - `frequency_penalty` — Penalize token frequency
  - `num_predict` — Max tokens to generate

**Response (200 OK):**
```json
{
  "model": "qwen2:1.5b",
  "created_at": "2026-01-31T10:00:00Z",
  "message": {"role": "assistant", "content": "Hi there!"},
  "done": true,
  "done_reason": "stop",
  "total_duration": 1234567890,
  "load_duration": 123456789,
  "prompt_eval_count": 10,
  "prompt_eval_duration": 123456789,
  "eval_count": 20,
  "eval_duration": 987654321,
  "context": [1, 2, 3, 4, 5]
}
```

**Streaming Response (stream=true):**
Multiple JSON objects with `done: false` followed by final object with `done: true` and performance metrics.

**Example:**
```bash
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b","messages":[{"role":"user","content":"Hello"}],"stream":false,"keep_alive":-1}'
```

## POST /api/generate

Runs single-shot text generation.

**Request:**
```json
{
  "model": "qwen2:1.5b",
  "prompt": "Hello",
  "stream": true,
  "keep_alive": -1,
  "suffix": "\n",
  "format": "json",
  "raw": false,
  "template": "{{.Prompt}}",
  "options": {
    "temperature": 0.7,
    "seed": 42,
    "top_k": 40,
    "top_p": 0.9,
    "frequency_penalty": 0.0,
    "num_predict": 128
  }
}
```

**Parameters:**
- `model` (required) — Model name
- `prompt` (required) — Input text
- `stream` (optional, default: true) — Stream response tokens
- `keep_alive` (optional, default: 300) — Keep model loaded for N seconds; `-1` = indefinite, `0` = unload immediately
- `suffix` (optional) — Text to append after generation
- `format` (optional) — Response format (e.g., `"json"`)
- `raw` (optional, default: false) — Skip prompt template formatting
- `template` (optional) — Custom response template
- `images` (optional) — Array of base64-encoded images for multimodal models
- `options` (optional) — Model parameters (same as `/api/chat`)

**Response (200 OK):**
```json
{
  "model": "qwen2:1.5b",
  "created_at": "2026-01-31T10:00:00Z",
  "response": "Hello! How can I help you?",
  "done": true,
  "done_reason": "stop",
  "total_duration": 1234567890,
  "load_duration": 123456789,
  "prompt_eval_count": 5,
  "prompt_eval_duration": 123456789,
  "eval_count": 15,
  "eval_duration": 987654321,
  "context": [1, 2, 3, 4, 5]
}
```

**Streaming Response (stream=true):**
Multiple JSON objects with partial `response` text and `done: false`, followed by final object with complete metrics.

**Example:**
```bash
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b","prompt":"Hello","keep_alive":-1}'
```

## DELETE /api/delete

Deletes a model from the local cache.

**Request:**
```json
{"model":"qwen2:1.5b"}
```

**Response:**
- `200 OK` on success (empty response body)
- `404 Not Found` if model doesn't exist

**Error Response (404):**
```json
{"code":"not_found","error":"model not found"}
```

**Example:**
```bash
curl -X DELETE http://localhost:11434/api/delete \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b"}'
```

## POST /v1/chat/completions

OpenAI-compatible chat completion endpoint. Provides compatibility with OpenAI client libraries and tools expecting the standard OpenAI API format.

**Request:**
```json
{
  "model": "qwen2:1.5b",
  "messages": [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "Hello"}
  ],
  "temperature": 0.7,
  "stream": false,
  "seed": 42,
  "top_p": 0.9,
  "frequency_penalty": 0.0,
  "presence_penalty": 0.0,
  "max_tokens": 128,
  "max_completion_tokens": 128,
  "n": 1
}
```

**Parameters:**
- `model` (required) — Model name
- `messages` (required) — Array of message objects
- `temperature` (optional) — Sampling temperature (0.0-2.0)
- `stream` (optional, default: false) — Stream response
- `seed` (optional) — Random seed for reproducibility
- `top_p` (optional) — Nucleus sampling threshold
- `frequency_penalty` (optional) — Penalize repeated tokens
- `presence_penalty` (optional) — Penalize tokens based on presence
- `max_tokens` (optional) — Maximum tokens to generate
- `max_completion_tokens` (optional) — Alias for `max_tokens`
- `n` (optional, default: 1) — Number of completions to generate

**Response (200 OK):**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "qwen2:1.5b",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hi there!"},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}
}
```

**Streaming Response (stream=true):**
```
data: {"choices":[{"delta":{"content":"Hello"}}]}
data: [DONE]
```

**Example:**
```bash
curl -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"qwen2:1.5b",
    "messages":[{"role":"user","content":"Hello"}],
    "stream":false,
    "temperature":0.7
  }'
```

## Error Responses

Standard HTTP status codes are used:
- `400 Bad Request` for invalid payloads
- `404 Not Found` for missing models
- `503 Service Unavailable` if the device is unavailable

## Upstream Reference

See the official Ollama API documentation for full compatibility details:
https://github.com/ollama/ollama/blob/main/docs/api.md

Note: This service wraps `hailo-ollama` from the Hailo Developer Zone, which provides Ollama-compatible and OpenAI-compatible endpoints optimized for Hailo-10H NPU inference. Additional endpoints like `/api/ps` and `/api/show` are extensions providing introspection into the inference runtime.
