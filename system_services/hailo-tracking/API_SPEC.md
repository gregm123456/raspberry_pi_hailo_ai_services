# Hailo Tracking API

Base URL: `http://127.0.0.1:11443`

The service binds to loopback by default and does not provide authentication. JSON error responses use `{"error":"..."}` unless noted otherwise.

## GET /health

Process liveness check. Does not connect to Device Manager or load a model.

**Response (200):**

```json
{
  "status": "ok",
  "service": "hailo-tracking",
  "models_load_on_demand": true
}
```

## GET /health/ready

Checks that both configured HEF files exist and that Device Manager responds to a ping. It does not load either HEF.

- **200:** `{"status":"ready","models":["stark_lightning_repvgg_a0","bytetrack_tiny_mot17"],"model_loading":"on demand"}`
- **503:** Missing models and/or Device Manager error details.

## GET /v1/info

Returns model input shapes, available sources, and service limits.

## POST /v1/video/preview

Accepts `multipart/form-data` with one `video` file and returns the first decodable frame as `image/jpeg`. The response includes `X-Image-Width` and `X-Image-Height`.

```bash
curl -F video=@clip.mp4 http://127.0.0.1:11443/v1/video/preview -o first-frame.jpg
```

Errors: **400** for an unreadable video or a video without frames; **413** if the upload exceeds 64 MiB.

## POST /v1/camera/preview?source=usb|csi

Captures one frame and returns `image/jpeg` with width/height headers. The default source is `usb`. USB capture uses the configured V4L2 device; CSI capture invokes `rpicam-still`.

```bash
curl -X POST 'http://127.0.0.1:11443/v1/camera/preview?source=usb' -o camera.jpg
```

Errors: **400** for an invalid source; **503** if camera access or capture fails.

## POST /v1/track/video

Accepts `multipart/form-data` with one `video` file, a required `mode`, and optional tracking coordinates.

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `video` | file | Yes | Input video |
| `mode` | string | Yes | `stark` or `bytetrack` |
| `x`, `y`, `width`, `height` | finite numbers | STARK only | Initial box in pixels of the first frame |

ByteTrack rejects supplied target coordinates. STARK requires all four coordinates and the box must fit within the first frame.

```bash
curl -F video=@clip.mp4 -F mode=stark \
  -F x=120 -F y=80 -F width=100 -F height=160 \
  http://127.0.0.1:11443/v1/track/video -o tracked.mp4
```

**Success (200):** `video/mp4`, with JSON result metadata in `X-Tracking-Metadata`, including frames processed, dimensions, inference time, and unique track count.

Errors: **400** for invalid input or unsupported video; **413** for oversized uploads; **503** for Device Manager inference failures; **500** if the output cannot be produced or exceeds 80 MiB.

## POST /v1/track/camera

Accepts JSON to record a camera clip and track it:

```json
{
  "source": "usb",
  "mode": "bytetrack",
  "duration_seconds": 5
}
```

For `stark`, include numeric `x`, `y`, `width`, and `height` values for the recorded clip's first frame.

- `source`: `usb` (default) or `csi`.
- `mode`: required; `stark` or `bytetrack`.
- `duration_seconds`: number from 1 through 20; defaults to 5.

Success and errors match `/v1/track/video`. Camera capture failures or temporary USB captures larger than 64 MiB return **503**.
