# Hailo Piper TTS API Specification

REST API for text-to-speech synthesis using Piper TTS models on Raspberry Pi 5.

**Base URL:** `http://localhost:5003`

## Endpoints

### Health Check

Check service status and model information.

**Endpoint:** `GET /health`

**Response (200 OK):**

```json
{
  "status": "healthy",
  "service": "hailo-piper",
  "model_loaded": true,
  "model_info": {
    "model_path": "/var/lib/hailo-piper/models/en_US-lessac-medium.onnx",
    "sample_rate": 22050,
    "num_speakers": 1,
    "language": "en-us"
  }
}
```

---

### Synthesize Speech (OpenAI-compatible)

Synthesize speech from text input. Compatible with OpenAI's `/v1/audio/speech` endpoint.

**Endpoint:** `POST /v1/audio/speech`

**Request Headers:**
- `Content-Type: application/json`

**Request Body:**

```json
{
  "input": "Text to synthesize",
  "model": "piper",
  "voice": "default",
  "response_format": "wav",
  "speed": 1.0
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input` | string | Yes | Text to synthesize (max 5000 chars) |
| `model` | string | No | Model identifier (always "piper") |
| `voice` | string | No | Voice ID (default: "default") |
| `response_format` | string | No | Output format: "wav" or "pcm" (default: "wav") |
| `speed` | float | No | Speech speed multiplier (not yet implemented) |

**Response (200 OK):**

Binary audio data (WAV format)

**Response Headers:**
- `Content-Type: audio/wav`
- `Content-Disposition: attachment; filename="speech.wav"`

**Error Responses:**

```json
// 400 Bad Request
{
  "error": "Missing 'input' field"
}

// 400 Bad Request (text too long)
{
  "error": "Text too long (max 5000 characters)"
}

// 400 Bad Request (invalid format)
{
  "error": "Unsupported format: mp3"
}

// 500 Internal Server Error
{
  "error": "Synthesis failed"
}
```

**Example:**

```bash
curl -X POST http://localhost:5003/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello world!"}' \
  --output speech.wav
```

---

### Synthesize (Alternative Endpoint)

Alternative synthesis endpoint with simplified parameters.

**Endpoint:** `POST /v1/synthesize`

**Request Headers:**
- `Content-Type: application/json`

**Request Body:**

```json
{
  "text": "Text to synthesize",
  "format": "wav"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Text to synthesize (max 5000 chars) |
| `format` | string | No | Output format: "wav" (default: "wav") |

**Response (200 OK):**

Binary audio data (WAV format)

**Example:**

```bash
curl -X POST http://localhost:5003/v1/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Testing Piper TTS"}' \
  --output test.wav
```

---

### List Voices

Get information about available voice models.

**Endpoint:** `GET /v1/voices`

**Response (200 OK):**

```json
{
  "voices": [
    {
      "id": "default",
      "name": "en_US-lessac-medium",
      "language": "en-us",
      "gender": "neutral",
      "sample_rate": 22050
    }
  ]
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Voice identifier |
| `name` | string | Human-readable voice name |
| `language` | string | Language code (e.g., "en-us") |
| `gender` | string | Voice gender ("male", "female", "neutral") |
| `sample_rate` | integer | Audio sample rate in Hz |

**Example:**

```bash
curl http://localhost:5003/v1/voices
```

---

## Error Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Endpoint not found |
| 500 | Internal Server Error |

## Common Error Responses

### Missing Required Field

```json
{
  "error": "Missing 'input' field"
}
```

### Text Too Long

```json
{
  "error": "Text too long (max 5000 characters)"
}
```

### Unsupported Format

```json
{
  "error": "Unsupported format: mp3"
}
```

### Synthesis Failed

```json
{
  "error": "Synthesis failed"
}
```

## Rate Limiting

No rate limiting is currently implemented. For production use, consider adding rate limiting at the reverse proxy level.

## Authentication

No authentication is required. For production deployments, consider:
- Running behind a reverse proxy with authentication
- Using a firewall to restrict access
- Implementing API key authentication

## Audio Formats

Currently supported formats:
- **WAV:** 16-bit PCM, mono, 22050 Hz (default)
- **PCM:** Raw 16-bit PCM audio data

## Text Preprocessing

The service automatically:
- Normalizes whitespace
- Handles basic punctuation
- Supports UTF-8 text
- Preserves sentence boundaries

## Limitations

- Maximum text length: 5000 characters per request
- Single voice per request
- No real-time streaming (full synthesis before response)
- WAV format only (no MP3/OGG support yet)

## Client Libraries

### Python Example

```python
import requests
from pathlib import Path

class PiperTTSClient:
    def __init__(self, base_url="http://localhost:5003"):
        self.base_url = base_url
    
    def health(self):
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def synthesize(self, text, output_file=None):
        response = requests.post(
            f"{self.base_url}/v1/audio/speech",
            json={"input": text},
            timeout=30
        )
        
        if response.status_code == 200:
            if output_file:
                Path(output_file).write_bytes(response.content)
            return response.content
        else:
            raise Exception(response.json().get("error", "Unknown error"))
    
    def list_voices(self):
        response = requests.get(f"{self.base_url}/v1/voices")
        return response.json()

# Usage
client = PiperTTSClient()
print(client.health())
client.synthesize("Hello world!", "output.wav")
print(client.list_voices())
```

### JavaScript Example

```javascript
const axios = require('axios');
const fs = require('fs');

class PiperTTSClient {
  constructor(baseURL = 'http://localhost:5003') {
    this.baseURL = baseURL;
  }

  async health() {
    const response = await axios.get(`${this.baseURL}/health`);
    return response.data;
  }

  async synthesize(text, outputFile) {
    const response = await axios.post(
      `${this.baseURL}/v1/audio/speech`,
      { input: text },
      { responseType: 'arraybuffer' }
    );

    if (outputFile) {
      fs.writeFileSync(outputFile, response.data);
    }
    return response.data;
  }

  async listVoices() {
    const response = await axios.get(`${this.baseURL}/v1/voices`);
    return response.data;
  }
}

// Usage
const client = new PiperTTSClient();
(async () => {
  console.log(await client.health());
  await client.synthesize('Hello world!', 'output.wav');
  console.log(await client.listVoices());
})();
```

## Version History

- **v1.0.0** - Initial release with basic TTS functionality
