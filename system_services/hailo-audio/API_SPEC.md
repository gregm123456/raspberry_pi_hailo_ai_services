# API Specification

Base URL: `http://localhost:11441`

## `GET /health`

Returns service health and whether the model loaded, e.g.
`{"status":"ok","service":"hailo-audio","model_loaded":true}`.

## `GET /ready`

Returns `{"status":"ready","model":"yamnet"}` when available; otherwise
HTTP 503.

## `POST /v1/classify?top_k=5`

Multipart form field `file` must contain an uncompressed PCM WAV. `top_k` is
an integer from 1 to 20.

Example response:

```json
{
  "model": "yamnet",
  "duration_seconds": 2.4,
  "patch_count": 4,
  "inference_time_ms": 52.3,
  "predictions": [
    {"class_id": 0, "label": "Speech", "score": 0.83}
  ]
}
```

Scores are mean sigmoid probabilities over the audio's 0.96-second windows.
Invalid audio and options return HTTP 400; unavailable model/device errors are
reported as server errors.
