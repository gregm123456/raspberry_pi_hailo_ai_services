# Hailo Super-Resolution API

Base URL: `http://127.0.0.1:11442`

## `GET /health`

Returns service and model metadata without loading the HEF:

```json
{
  "status": "ok",
  "model": "spanf_x4",
  "input_shape": [512, 512, 3],
  "scale_factor": 4,
  "max_input_pixels": 4000000
}
```

## `GET /health/ready`

Pings `hailo-device-manager`. Returns HTTP 200 when it is reachable and HTTP
503 otherwise.

## `POST /v1/super-resolve`

Request JSON:

```json
{
  "image": "data:image/jpeg;base64,<encoded image>"
}
```

The image must be a base64 data URI. PNG and JPEG are recommended. The decoded
image may have any aspect ratio but must contain no more than 4,000,000 pixels.
Images are processed as overlapping 512x512 RGB tiles and returned at four
times their original width and height.

Successful response:

```json
{
  "image": "data:image/jpeg;base64,<encoded 4x output>",
  "input_width": 512,
  "input_height": 512,
  "output_width": 2048,
  "output_height": 2048,
  "scale_factor": 4,
  "tiles_processed": 1,
  "inference_time_ms": 850.5
}
```

Invalid JSON or image data returns HTTP 400. Images above the pixel limit return
HTTP 400. Device Manager or inference failures return HTTP 503 with an `error`
message.

## Example

```python
import base64
import requests

with open("input.jpg", "rb") as image_file:
    encoded = base64.b64encode(image_file.read()).decode("ascii")

response = requests.post(
    "http://127.0.0.1:11442/v1/super-resolve",
    json={"image": f"data:image/jpeg;base64,{encoded}"},
    timeout=600,
)
response.raise_for_status()
result = response.json()
with open("upscaled.jpg", "wb") as output_file:
    output_file.write(base64.b64decode(result["image"].split(",", 1)[1]))
```
