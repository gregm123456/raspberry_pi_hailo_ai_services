# Hailo Device Manager API

Base transport: Unix socket at `/run/hailo/device.sock`

Authentication: none (local socket permissions control access).

Protocol: length-prefixed JSON messages over a Unix socket. Each request and response is a single JSON object.

## Request Envelope

All requests are JSON objects with an `action` field.

Common fields:
- `action` (string, required)
- `request_id` (string, optional) - echoed back in the response

Example:
```json
{
  "action": "ping",
  "request_id": "abc-123"
}
```

## Response Envelope

Common fields:
- `status` (string) - typically `ok` for success
- `error` (string) - present on failure
- `request_id` (string) - echoed back if provided in the request

Example success:
```json
{
  "status": "ok",
  "uptime_seconds": 12.3,
  "request_id": "abc-123"
}
```

Example error:
```json
{
  "error": "Model file not found: /path/to/model.hef",
  "request_id": "abc-123"
}
```

## Actions

### ping
Check connection and uptime.

Request:
```json
{
  "action": "ping",
  "request_id": "..."
}
```

Response (200 OK):
```json
{
  "status": "ok",
  "device_id": "0001:01:00.0",
  "loaded_models": [],
  "uptime_seconds": 123.4,
  "socket_path": "/run/hailo/device.sock",
  "queue_depth": 0,
  "request_id": "..."
}
```

### status
Get device status and loaded model list.

Request:
```json
{
  "action": "status",
  "request_id": "..."
}
```

Response (200 OK):
```json
{
  "status": "ok",
  "device_id": "0001:01:00.0",
  "loaded_models": [
    {
      "model_type": "vlm",
      "model_path": "/path/to/model.hef",
      "loaded_at": 1700000000.0,
      "last_used": 1700000001.5
    }
  ],
  "uptime_seconds": 123.4,
  "socket_path": "/run/hailo/device.sock",
  "queue_depth": 1,
  "request_id": "..."
}
```

### load_model
Load a model into device memory.

Request:
```json
{
  "action": "load_model",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "model_params": {},
  "request_id": "..."
}
```

Response (200 OK):
```json
{
  "status": "ok",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "message": "Model loaded",
  "request_id": "..."
}
```

### infer
Run inference. If the model is not loaded, it is loaded first using the provided `model_params`.

Request:
```json
{
  "action": "infer",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "model_params": {},
  "input_data": {},
  "request_id": "..."
}
```

Response (200 OK):
```json
{
  "status": "ok",
  "result": {},
  "inference_time_ms": 42,
  "request_id": "..."
}
```

### unload_model
Unload a model from device memory.

Request:
```json
{
  "action": "unload_model",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "request_id": "..."
}
```

Response (200 OK):
```json
{
  "status": "ok",
  "message": "Model unloaded",
  "request_id": "..."
}
```

## Model Types

Supported `model_type` values:
- `vlm` - Hailo GenAI VLM via `hailo_platform.genai.VLM`
- `vlm_chat` - VLM chat using `VLM.generate_all`
- `clip` - CLIP image/text encoders using `create_infer_model`
- `whisper` - Speech-to-text transcription via `hailo_platform.genai.Speech2Text`
- `ocr` - Optical character recognition (detection + recognition) with device manager serialization
- `depth` - Monocular depth estimation (e.g., scdepthv3)
  - Input: Preprocessed image tensor (float32 or uint8, [1,3,H,W] in NCHW format)
  - Output: Depth map tensor (float32, [1,1,H,W] in NCHW format)

## Tensor Payload Format

Some model types (for example `vlm_chat` and `clip`) send tensors in `input_data`.

Tensor object:
```json
{
  "dtype": "uint8",
  "shape": [1, 224, 224, 3],
  "data_b64": "..."
}
```

- `dtype`: NumPy dtype string
- `shape`: array shape
- `data_b64`: base64-encoded raw tensor bytes

## Error Handling

Errors are returned in a JSON object with an `error` field.

Common errors:
- `model_path required`
- `model_path and input_data required`
- `Unsupported model_type: <value>`
- `tensor must include dtype, shape, and data_b64`
- `Message too large: <bytes> bytes`

## Limits

- Maximum message size: `HAILO_DEVICE_MAX_MESSAGE_BYTES` (default 8 MiB)
- Socket path: `HAILO_DEVICE_SOCKET` (default `/run/hailo/device.sock`)

## Example Client Usage

Python async client example:
```python
from device_client import HailoDeviceClient

async with HailoDeviceClient() as client:
    await client.load_model("/path/to/model.hef", model_type="vlm")
    result = await client.infer("/path/to/model.hef", {"prompt": "Hello"}, model_type="vlm")
```
