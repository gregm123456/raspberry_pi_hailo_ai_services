# Hailo Whisper API Specification

REST API for speech-to-text transcription. OpenAI Whisper API-compatible.

## Base URL

```
http://localhost:11436
```

Default port: `11436` (configurable in `/etc/hailo/hailo-whisper.yaml`)

---

## Endpoints

### Health Check

#### `GET /health`

Service status and statistics.

**Response:**
```json
{
  "status": "ok",
  "model": "whisper-small-int8",
  "model_loaded": true,
  "uptime_seconds": 3600.5,
  "transcriptions_processed": 42
}
```

**Status Codes:**
- `200 OK` - Service operational

---

### Readiness Probe

#### `GET /health/ready`

Kubernetes-style readiness check.

**Response (Ready):**
```json
{
  "ready": true
}
```

**Response (Not Ready):**
```json
{
  "ready": false,
  "reason": "model_loading"
}
```

**Status Codes:**
- `200 OK` - Service ready
- `503 Service Unavailable` - Service not ready

---

### List Models

#### `GET /v1/models`

List available Whisper models.

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "whisper-small-int8",
      "object": "model",
      "created": 1706745600,
      "owned_by": "hailo"
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success

---

### Transcribe Audio

#### `POST /v1/audio/transcriptions`

Transcribe audio file to text.

**Content-Type:** `multipart/form-data`

**Required Fields:**
- `file` (file) - Audio file to transcribe
  - Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg, flac
  - Max size: 25 MB
  - Max duration: 300 seconds (configurable)
- `model` (string) - Model ID (e.g., `"whisper-small"`)

**Optional Fields:**
- `language` (string) - ISO 639-1 language code (e.g., `"en"`, `"es"`, `"fr"`)
  - If omitted, language is auto-detected
- `prompt` (string) - Optional text to guide the model's style
- `response_format` (string) - Response format
  - `"json"` (default) - Simple JSON with text only
  - `"verbose_json"` - JSON with segments and metadata
  - `"text"` - Plain text response
  - `"srt"` - SRT subtitle format
  - `"vtt"` - WebVTT subtitle format
- `temperature` (float) - Sampling temperature (0.0 to 1.0)
  - Default: 0.0 (greedy decoding)

---

### Response Formats

#### JSON (default)

```json
{
  "text": "Hello, this is a test transcription."
}
```

#### Verbose JSON

```json
{
  "task": "transcribe",
  "language": "en",
  "duration": 2.5,
  "text": "Hello, this is a test transcription.",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "Hello, this is a test transcription.",
      "tokens": [1, 2, 3, 4, 5],
      "temperature": 0.0,
      "avg_logprob": -0.5,
      "compression_ratio": 1.2,
      "no_speech_prob": 0.05
    }
  ]
}
```

#### Text

```
Hello, this is a test transcription.
```

#### SRT

```
1
00:00:00,000 --> 00:00:02,500
Hello, this is a test transcription.
```

#### VTT

```
WEBVTT

00:00:00.000 --> 00:00:02.500
Hello, this is a test transcription.
```

---

### Status Codes

#### Success
- `200 OK` - Request successful

#### Client Errors
- `400 Bad Request` - Invalid request (missing fields, invalid format)
- `413 Payload Too Large` - Audio file exceeds size limit

#### Server Errors
- `500 Internal Server Error` - Inference or processing failure
- `503 Service Unavailable` - Model not loaded

---

## Error Response Format

All error responses follow this structure:

```json
{
  "error": {
    "message": "Missing 'file' field",
    "type": "invalid_request_error"
  }
}
```

**Error Types:**
- `invalid_request_error` - Client-side error (bad input)
- `internal_error` - Server-side error (processing failure)

---

## Examples

### cURL

```bash
# Basic transcription
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small"

# Verbose JSON with language
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small" \
  -F language="en" \
  -F response_format="verbose_json"

# SRT subtitles
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small" \
  -F response_format="srt" \
  -o subtitles.srt
```

### Python (requests)

```python
import requests

url = "http://localhost:11436/v1/audio/transcriptions"

with open("audio.mp3", "rb") as f:
    files = {"file": f}
    data = {"model": "whisper-small", "language": "en"}
    response = requests.post(url, files=files, data=data)
    result = response.json()
    print(result["text"])
```

### Python (OpenAI SDK)

The service is compatible with the OpenAI Python SDK:

```python
from openai import OpenAI

client = OpenAI(
    api_key="not-needed",
    base_url="http://localhost:11436/v1"
)

with open("audio.mp3", "rb") as f:
    transcript = client.audio.transcriptions.create(
        model="whisper-small",
        file=f,
        response_format="verbose_json"
    )
    print(transcript.text)
```

### JavaScript (fetch)

```javascript
const formData = new FormData();
formData.append('file', audioBlob, 'audio.mp3');
formData.append('model', 'whisper-small');
formData.append('language', 'en');

const response = await fetch('http://localhost:11436/v1/audio/transcriptions', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log(result.text);
```

---

## Supported Languages

When specifying `language`, use ISO 639-1 codes:

| Language   | Code |
|------------|------|
| English    | en   |
| Spanish    | es   |
| French     | fr   |
| German     | de   |
| Italian    | it   |
| Portuguese | pt   |
| Chinese    | zh   |
| Japanese   | ja   |
| Korean     | ko   |
| Russian    | ru   |
| Arabic     | ar   |
| Hindi      | hi   |

Full list: https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes

---

## Rate Limits

No rate limiting is enforced by default. Consider implementing rate limiting at the reverse proxy level for production deployments.

---

## Compatibility

This API is compatible with:
- OpenAI Whisper API
- OpenAI Python SDK (>= 1.0.0)
- Whisper.cpp HTTP server
- faster-whisper API

Any client that supports the OpenAI Whisper API format should work with this service.
