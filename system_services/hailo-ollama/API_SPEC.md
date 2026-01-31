# Hailo Ollama API Specification

Base URL: `http://localhost:11434`

This service exposes the upstream `hailo-ollama` API. Endpoints and payloads mirror the Ollama API.

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

Lists available models.

**Response (200 OK):**
```json
{"models":[{"name":"qwen2:1.5b","size":"<size>"}]}
```

**Example:**
```bash
curl http://localhost:11434/api/tags
```

## POST /api/pull

Downloads a model into the local cache.

**Request:**
```json
{"name":"qwen2:1.5b"}
```

**Response (200 OK):** streaming JSON progress.

**Example:**
```bash
curl -X POST http://localhost:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name":"qwen2:1.5b"}'
```

## POST /api/chat

Runs chat inference.

**Request:**
```json
{
  "model": "qwen2:1.5b",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false
}
```

**Response (200 OK):**
```json
{"message":{"role":"assistant","content":"Hi"}}
```

**Example:**
```bash
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

## POST /api/generate

Runs single-shot text generation.

**Request:**
```json
{"model":"qwen2:1.5b","prompt":"Hello"}
```

**Response (200 OK):** streaming JSON tokens.

**Example:**
```bash
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2:1.5b","prompt":"Hello"}'
```

## Error Responses

Standard HTTP status codes are used:
- `400 Bad Request` for invalid payloads
- `404 Not Found` for missing models
- `503 Service Unavailable` if the device is unavailable

## Upstream Reference

See the official Ollama API documentation for full compatibility details:
https://github.com/ollama/ollama/blob/main/docs/api.md
