# Hailo Tracking Service

Provides video object tracking on Raspberry Pi 5 with Hailo-10H. STARK follows one target selected by pixel coordinates in the first frame; ByteTrack Tiny detects pedestrians and associates detections across frames. Videos can be uploaded or captured from the attached USB camera or an optional CSI camera.

## Prerequisites

- Raspberry Pi OS Trixie, Python 3.10+, and the Hailo-10H driver/runtime.
- The `hailo-device-manager` service installed and running; verify with `hailortcli fw-control identify`.
- The `hailo-device-mgr` group and, for USB cameras, the `video` group.
- For CSI capture, a connected CSI camera and `rpicam-still` / `rpicam-vid`.
- Network access during installation to fetch the public Model Zoo HEFs.

The installer creates an isolated Python virtual environment in `/opt/hailo-tracking/venv`. It downloads the two pinned Hailo-10H v5.5.0 HEFs from the public Hailo Model Zoo; no Developer Zone downloads are required.

## Installation

```bash
sudo ./install.sh
sudo systemctl status hailo-tracking.service
curl http://127.0.0.1:11443/health/ready
```

The service binds to loopback by default and is managed by systemd. The installer enables and starts it. Model inference is requested through Device Manager, not directly by this service.

## Configuration

The systemd unit sets model paths and the default bind address. Override settings with a systemd drop-in if needed:

```bash
sudo systemctl edit hailo-tracking.service
```

Supported environment variables:

| Variable | Default | Description |
|---|---|---|
| `HAILO_TRACKING_HOST` | `127.0.0.1` | API bind address |
| `HAILO_TRACKING_PORT` | `11443` | API port |
| `HAILO_TRACKING_STARK_HEF` | `/var/lib/hailo-tracking/models/stark_lightning_repvgg_a0.hef` | STARK HEF |
| `HAILO_TRACKING_BYTETRACK_HEF` | `/var/lib/hailo-tracking/models/bytetrack_tiny_mot17.hef` | ByteTrack HEF |
| `HAILO_TRACKING_USB_DEVICE` | `/dev/video0` | USB camera device |
| `HAILO_TRACKING_USB_WIDTH` / `HAILO_TRACKING_USB_HEIGHT` | `640` / `480` | Requested USB capture size |
| `HAILO_TRACKING_CSI_INDEX` | `0` | CSI camera index |
| `HAILO_TRACKING_CSI_WIDTH` / `HAILO_TRACKING_CSI_HEIGHT` | `1280` / `720` | Requested CSI capture size |

After changing a drop-in, run `sudo systemctl daemon-reload && sudo systemctl restart hailo-tracking.service`.

## Basic usage

Preview an uploaded video:

```bash
curl -F video=@clip.mp4 http://127.0.0.1:11443/v1/video/preview -o first-frame.jpg
```

Run ByteTrack-style pedestrian tracking:

```bash
curl -F video=@clip.mp4 -F mode=bytetrack \
  http://127.0.0.1:11443/v1/track/video -o tracked.mp4
```

Run STARK with a first-frame box `(x, y, width, height)` in original-frame pixels:

```bash
curl -F video=@clip.mp4 -F mode=stark -F x=120 -F y=80 -F width=100 -F height=160 \
  http://127.0.0.1:11443/v1/track/video -o tracked.mp4
```

Capture and track a five-second USB-camera clip:

```bash
curl -H 'Content-Type: application/json' \
  -d '{"source":"usb","mode":"bytetrack","duration_seconds":5}' \
  http://127.0.0.1:11443/v1/track/camera -o tracked.mp4
```

The portal includes a Tracking tab for previewing a source, entering a STARK box, and downloading the result. Manage the service with:

```bash
sudo systemctl status hailo-tracking.service
sudo journalctl -u hailo-tracking.service -f
sudo systemctl restart hailo-tracking.service
```

## Limits

- Uploads and temporary USB camera captures are limited to 64 MiB, videos to 600 frames, frames to 8 megapixels, camera clips to 1–20 seconds, and generated MP4s to 80 MiB.
- The API does not require authentication and binds only to localhost by default.
- STARK coordinates must fit within the first frame. ByteTrack Tiny is pedestrian-oriented.
- The current ByteTrack-style association is a lightweight confidence/IoU tracker, not the reference Kalman-filter/Hungarian ByteTrack implementation.
- CSI camera capture depends on the connected hardware and has not been validated on this device.

## Detailed documentation

- [API_SPEC.md](./API_SPEC.md) — HTTP endpoints and request/response formats
- [ARCHITECTURE.md](./ARCHITECTURE.md) — components, constraints, and known limitations
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — diagnostics and common fixes
