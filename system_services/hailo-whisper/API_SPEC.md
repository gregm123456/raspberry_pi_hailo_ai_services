# Hailo Whisper API Specification

REST API for speech-to-text transcription. OpenAI Whisper API-compatible.

## Base URL

```
http://localhost:11437
```

Default port: `11437` (configurable in `/etc/hailo/hailo-whisper.yaml`)

---

## Endpoints

### Health Check

#### `GET /health`

Service status and statistics.

**Response:**
```json
{
  "status": "ok",
  "model": "Whisper-Base",
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
      "id": "Whisper-Base",
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

**Content-Type:** `multipart/form-data` *(strictly required)*

This endpoint follows the [OpenAI Whisper API specification](https://platform.openai.com/docs/api-reference/audio/createTranscription) and **only** accepts `multipart/form-data` uploads. Raw audio payloads (e.g., `Content-Type: audio/wav` with audio as the request body) are not supported and will return `415 Unsupported Media Type`.

Clients without local file paths (browser apps, mobile, streaming pipelines) can still use this endpoint by uploading audio data as an in-memory blob within the multipart form. See examples below.

**Required Fields:**
- `file` (file) - Audio file to transcribe
  - Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg, flac
  - Max size: 25 MB
  - Max duration: 300 seconds (configurable)
- `model` (string) - Model ID (default: `"Whisper-Base"`)

**Optional Fields:**
- `language` (string) - ISO 639-1 language code (e.g., `"en"`, `"es"`, `"fr"`)
  - If omitted, language is auto-detected
- `prompt` (string) - Optional text to guide the model's style *(parsed but not currently supported by backend)*
- `response_format` (string) - Response format
  - `"json"` (default) - Simple JSON with text only
  - `"verbose_json"` - JSON with segments and metadata
  - `"text"` - Plain text response
  - `"srt"` - SRT subtitle format
  - `"vtt"` - WebVTT subtitle format
- `temperature` (float) - Sampling temperature (0.0 to 1.0) *(parsed but uses config default)*
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
- `415 Unsupported Media Type` - Content-Type is not `multipart/form-data`

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
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base"

# Verbose JSON with language
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base" \
  -F language="en" \
  -F response_format="verbose_json"

# SRT subtitles
curl -X POST http://localhost:11437/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="Whisper-Base" \
  -F response_format="srt" \
  -o subtitles.srt

# Streaming from stdin (no local file required)
ffmpeg -i source.mp4 -f mp3 -ab 128k - | \
  curl -X POST http://localhost:11437/v1/audio/transcriptions \
    -F file="@-;filename=audio.mp3" \
    -F model="Whisper-Base"

# Upload from URL without local save
curl -s https://example.com/audio.mp3 | \
  curl -X POST http://localhost:11437/v1/audio/transcriptions \
    -F file="@-;filename=audio.mp3" \
    -F model="Whisper-Base"
```

### Python (requests)

```python
import requests

url = "http://localhost:11437/v1/audio/transcriptions"

with open("audio.mp3", "rb") as f:
    files = {"file": f}
    data = {"model": "Whisper-Base", "language": "en"}
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
    base_url="http://localhost:11437/v1"
)

// Browser: Upload from file input
const fileInput = document.querySelector('input[type="file"]');
const file = fileInput.files[0];

const formData = new FormData();
formData.append('file', file);
formData.append('model', 'Whisper-Base');
formData.append('language', 'en');

const response = await fetch('http://localhost:11437/v1/audio/transcriptions', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log(result.text);

// Browser: Upload from in-memory blob (e.g., MediaRecorder output)
const audioBlob = await recorder.stop(); // Blob from recording
const formData = new FormData();
formData.append('file', audioBlob, 'recording.webm');
formData.append('model', 'Whisper-Base');

const response = await fetch('http://localhost:11437/v1/audio/transcriptions', {
  method: 'POST',
  body: formData
}
const formData = new FormData();
formData.append('file', audioBlob, 'audio.mp3');
formData.append('model', 'Whisper-Base');
formData.append('language', 'en');

const response = await fetch('http://localhost:11437/v1/audio/transcriptions', {
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
