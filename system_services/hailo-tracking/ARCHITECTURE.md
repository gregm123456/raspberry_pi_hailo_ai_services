# Hailo Tracking Architecture

## Purpose

Expose video preview and tracking APIs for Hailo-10H Model Zoo STARK and ByteTrack Tiny HEFs. The service handles video/camera I/O and post-processing while the shared Device Manager owns HailoRT access.

## Components

- `hailo_tracking_service.py` provides an aiohttp API, validates uploads and camera settings, and invokes USB/CSI capture backends.
- `tracking_pipeline.py` performs frame decoding/encoding, STARK crop and box mapping, ByteTrack Tiny tensor decoding/NMS, and lightweight track association.
- `portal_client.py` and the portal Tracking tab provide preview, control, and result download.
- The installer downloads both public v5.5.0 Hailo-10H HEFs to `/var/lib/hailo-tracking/models` and configures the service account to read them.
- `hailo-device-manager` loads the requested model only when inference is requested. Readiness checks do not load models.

## Tracking modes

**STARK** uses the first frame and a manually entered `(x, y, width, height)` box to build a template. It runs one search inference for each later frame and maps the normalized model box back into original-frame pixels.

**ByteTrack Tiny** detects pedestrians over three feature-map scales, applies NMS, then associates high- and low-confidence detections to active tracks using IoU and a simple velocity estimate. This is intentionally a small Pi-friendly ByteTrack-style implementation; it does not implement the reference Kalman filter and Hungarian assignment.

## Resource and deployment model

- systemd `Type=simple`, dedicated `hailo-tracking` account, and `hailo-device-mgr`/`video` supplementary groups.
- Default API bind is `127.0.0.1:11443`; systemd requires Device Manager.
- A service-level async lock serializes inference jobs. Camera capture has a separate lock and is recorded to a temporary MP4 before inference, so inference latency does not shorten the requested camera recording duration.
- Python dependencies are pinned in an isolated venv at `/opt/hailo-tracking/venv`.
- Limits: 64 MiB upload and USB capture, 600 frames per video, 8 megapixels per frame, 20-second maximum camera clip, and 80 MiB output.
- USB captures are staged as JPEG frames and encoded at the measured frame count divided by requested duration, so camera warm-up or a slow UVC frame cadence does not shorten playback duration.
- Only the service API is limited to 1 GiB RAM and 100% CPU quota; shared Device Manager resources are accounted separately.

## Known limitations

- Device Manager may evict other cached networks when tracker models are first loaded; the service intentionally does not warm models on startup.
- ByteTrack association is a simplified IoU/velocity implementation, not the full reference algorithm.
- STARK selection currently uses manual first-frame pixel coordinates rather than interactive drawing.
- USB behavior depends on V4L2 camera capabilities. The current USB device was confirmed to capture frames; CSI capture is implemented but not hardware-verified.
- Camera recording uses MP4 encoding through OpenCV for USB or `rpicam-vid` for CSI.

## Potential improvements

- Add interactive box selection to the portal.
- Implement full Kalman/Hungarian ByteTrack association if tracking quality warrants the CPU and code cost.
- Test CSI capture when hardware is connected and tune resolution/frame rate based on measured latency.
