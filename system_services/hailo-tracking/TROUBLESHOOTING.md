# Troubleshooting Hailo Tracking

## Service does not start

**Diagnose:**

```bash
sudo systemctl status hailo-tracking.service
sudo journalctl -u hailo-tracking.service -n 80 --no-pager
```

**Likely causes and fixes:**

- Confirm Device Manager is installed/running: `sudo systemctl status hailo-device-manager.service`.
- Confirm required groups exist: `getent group hailo-device-mgr video`.
- Check the pinned venv installation: `/opt/hailo-tracking/venv/bin/python -c 'import aiohttp, cv2, numpy'`.
- Re-run `sudo ./install.sh` after resolving missing dependencies.

## Readiness returns 503

**Diagnose:**

```bash
curl -i http://127.0.0.1:11443/health/ready
ls -l /var/lib/hailo-tracking/models/
sudo journalctl -u hailo-device-manager.service -n 60 --no-pager
```

Both HEFs must exist, and Device Manager must answer its ping. Re-run the installer if a model download is missing. Model loading is deferred until the first track request.

## Permission denied reading an HEF

**Diagnose:**

```bash
id hailo-tracking
ls -ld /var/lib/hailo-tracking /var/lib/hailo-tracking/models
ls -l /var/lib/hailo-tracking/models/*.hef
```

The service account must belong to `hailo-device-mgr`, and HEFs must be `root:hailo-device-mgr` with mode `640`. Re-run `sudo ./install.sh` to repair ownership and permissions.

## USB camera preview or recording fails

**Diagnose:**

```bash
ls -l /dev/video*
v4l2-ctl --device=/dev/video0 --all
id hailo-tracking
curl -i -X POST 'http://127.0.0.1:11443/v1/camera/preview?source=usb'
```

Check that the configured device exists and that the service account is in the `video` group. Override `HAILO_TRACKING_USB_DEVICE`, width, or height in a systemd drop-in if the camera uses a different path or supported format.

## CSI camera is unavailable

**Diagnose:**

```bash
command -v rpicam-still rpicam-vid
rpicam-hello --list-cameras
curl -i -X POST 'http://127.0.0.1:11443/v1/camera/preview?source=csi'
```

CSI support requires connected camera hardware and installed Raspberry Pi camera utilities. This backend has not been validated without a connected CSI camera.

## STARK rejects the target box

Preview the input first and use pixel coordinates from the original frame, not the scaled portal display. The box must have positive width/height and remain entirely inside the first frame. ByteTrack mode does not accept a target box.

## Tracking takes too long or rejects a video

Videos are limited to 600 frames and 8 megapixels per frame; uploads and temporary USB camera capture are limited to 64 MiB. Shorten or downscale the video before upload. For camera capture, duration must be from 1 to 20 seconds. Track runs are serialized in this service while other Device Manager clients may still compete for NPU capacity.

## CSI utility reports an unsupported option or codec

Inspect the command's stderr in the service journal and compare it with the installed `rpicam-vid --help`. CSI output currently requests MP4 via the libav encoder. Do not remove the camera lock or bypass the service limit; adjust the capture options only after verifying that the connected Pi OS utility supports them.
