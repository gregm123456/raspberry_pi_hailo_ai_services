# Hailo Pose Service Architecture

## Overview

The Hailo Pose service provides YOLOv8-based pose estimation on the Hailo-10H NPU via a REST API. It follows the same architectural patterns as other services in this repository, with pose-specific optimizations.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Client Applications                    │
│          (Python, curl, JavaScript, etc.)               │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP REST API
                      │ (port 11436)
┌─────────────────────▼───────────────────────────────────┐
│              hailo-pose-server (Python)                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │          aiohttp Web Server                       │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  APIHandler (Request Routing)               │  │  │
│  │  └──────────────┬──────────────────────────────┘  │  │
│  └─────────────────┼──────────────────────────────────┘  │
│  ┌─────────────────▼──────────────────────────────────┐  │
│  │         PoseService (Model Lifecycle)             │  │
│  │  - Model loading/unloading                        │  │
│  │  - Inference orchestration                        │  │
│  │  - Result post-processing                         │  │
│  └─────────────────┬──────────────────────────────────┘  │
└────────────────────┼────────────────────────────────────┘
                     │ HailoRT SDK
┌────────────────────▼────────────────────────────────────┐
│              Hailo-10H NPU Device                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │  YOLOv8-pose HEF Model                            │  │
│  │  - Backbone: Feature extraction                   │  │
│  │  - Head: Bounding box + keypoint detection        │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Component Design

### 1. PoseServiceConfig

**Purpose:** Configuration management from YAML → JSON → Python objects

**Responsibilities:**
- Load configuration from `/etc/xdg/hailo-pose/hailo-pose.json`
- Provide default values for all settings
- Validate configuration schema

**Key Settings:**
- Server: Host, port
- Model: Name, keep_alive policy
- Inference: Confidence/IoU thresholds, max detections
- Pose: Keypoint threshold, skeleton connections

### 2. PoseService

**Purpose:** Core inference service with model lifecycle management

**Responsibilities:**
- Initialize HailoRT model at startup
- Maintain persistent model in memory (if `keep_alive = -1`)
- Orchestrate inference pipeline
- Post-process outputs (NMS, keypoint extraction)

**Inference Pipeline:**
1. **Image Preprocessing:**
   - Decode image bytes (JPEG/PNG/WebP)
   - Resize to model input size (640x640 default)
   - Normalize pixel values (0-1 range)
   - Convert to CHW format (channels-first)

2. **NPU Inference:**
   - Copy preprocessed tensor to NPU input buffer
   - Trigger inference via HailoRT SDK
   - Read output tensors (bounding boxes + keypoint heatmaps)

3. **Post-Processing:**
   - Extract bounding box predictions (x, y, w, h, confidence)
   - Apply NMS (Non-Maximum Suppression) with IoU threshold
   - Extract keypoint coordinates from heatmaps
   - Filter by confidence thresholds
   - Format results in COCO keypoint format

### 3. APIHandler

**Purpose:** HTTP request handling and routing

**Endpoints:**
- `GET /health` - Service health check
- `GET /health/ready` - Readiness probe
- `GET /v1/models` - List available models
- `POST /v1/pose/detect` - Main inference endpoint

**Request Handling:**
- Multipart form data (for binary images)
- JSON with base64-encoded images
- Parameter validation and sanitization
- Error formatting

### 4. systemd Integration

**Unit File:** `/etc/systemd/system/hailo-pose.service`

**Key Configurations:**
- `Type=simple` - Foreground process (asyncio event loop)
- `User=hailo-pose` - Dedicated service user
- `Restart=always` - Auto-restart on failure
- `MemoryMax=2G` - Memory limit
- `CPUQuota=80%` - CPU quota (4 cores @ 80% = 3.2 cores)

**Environment Variables:**
- `XDG_CONFIG_HOME=/etc/xdg` - Config location
- `HAILO_PRINT_TO_SYSLOG=1` - HailoRT logs to journald
- `PYTHONUNBUFFERED=1` - Real-time log output

## Model Lifecycle

### Persistent Loading (Default)

**Configuration:** `model.keep_alive: -1`

**Behavior:**
1. Model loads at service startup (`initialize()`)
2. Stays resident in NPU memory indefinitely
3. Zero latency for subsequent requests
4. Unloads only on service shutdown (`shutdown()`)

**Advantages:**
- Consistent low latency (~30-60ms)
- No startup overhead for requests
- Predictable performance

**Trade-offs:**
- NPU memory allocated continuously (~1.5-2GB)
- Other services must budget around this allocation

### On-Demand Loading (Optional)

**Configuration:** `model.keep_alive: 0` or `model.keep_alive: 300`

**Behavior:**
1. Model loads on first request
2. Unloads after idle timeout (0 = immediate, N seconds)
3. First request has higher latency (~1-2s)

**Use When:**
- Intermittent usage patterns
- Memory must be shared with many services
- Acceptable to trade latency for resource efficiency

## Data Flow

### Request Processing

```
Client → HTTP POST /v1/pose/detect
  ↓
APIHandler.detect()
  ↓
Extract image data (multipart or base64)
  ↓
PoseService.detect_poses(image_data, params)
  ↓
[Image Preprocessing]
  - Decode image bytes
  - Resize to 640x640 (or config input_size)
  - Normalize and convert to tensor
  ↓
[NPU Inference via HailoRT]
  - Copy tensor to NPU input buffer
  - Run inference (~30-60ms)
  - Read output tensors
  ↓
[Post-Processing]
  - Extract bounding boxes (x, y, w, h, conf)
  - Apply NMS (remove overlapping detections)
  - Extract keypoints from heatmaps (17 per person)
  - Filter by confidence thresholds
  - Build skeleton connections
  ↓
Return JSON response
  ↓
Client receives result
```

## Resource Management

### Memory Budget

**YOLOv8s-pose (default):**
- Model weights: ~12 MB HEF
- NPU activation memory: ~1.2 GB
- Python process: ~300 MB
- **Total: ~1.5-2 GB**

**Concurrent Services:**
- Hailo-10H has ~4GB NPU memory
- Can run 2-3 pose estimation services concurrently
- Or 1 pose + 1 vision + 1 LLM service

### CPU Usage

- **Preprocessing:** ~20-30% CPU (1 core)
- **NPU Inference:** Minimal CPU (<5%)
- **Post-processing:** ~10-20% CPU (NMS, formatting)
- **Total per request:** ~30-50% CPU utilization

### Thermal Management

**Typical Load:**
- Idle: ~40-45°C
- Continuous inference (20 FPS): ~55-60°C
- Peak load: ~65-70°C

**Throttling:**
- Pi 5 throttles at 85°C
- Hailo-10H thermal limit: 105°C
- Recommendations: Passive heatsink or fan for sustained workloads

## Configuration Files

### YAML Config (`/etc/hailo/hailo-pose.yaml`)

**Purpose:** Human-editable configuration

**Sections:**
- `server`: Host, port
- `model`: Name, keep_alive policy
- `inference`: Thresholds, max detections, input size
- `pose`: Keypoint threshold, skeleton connections
- `resource_limits`: Memory/CPU limits (for systemd)

### JSON Config (`/etc/xdg/hailo-pose/hailo-pose.json`)

**Purpose:** Runtime configuration (read by Python service)

**Generated from YAML via `render_config.py`**

**Why JSON?**
- Faster parsing than YAML
- No external dependencies (stdlib only)
- XDG standard compliance

## Security Model

### User Isolation

- Service runs as dedicated `hailo-pose` user (no shell)
- Group membership for `/dev/hailo0` access
- No sudo or privilege escalation

### Filesystem Permissions

**Read-only:**
- `/etc/hailo/hailo-pose.yaml` (config)
- `/etc/xdg/hailo-pose/hailo-pose.json` (config)
- `/usr/local/bin/hailo-pose-server` (binary)

**Read-write:**
- `/var/lib/hailo-pose/` (state directory)
- `/var/lib/hailo-pose/models/` (model cache)
- `/var/lib/hailo-pose/cache/` (temporary files)

### Systemd Hardening

- `PrivateTmp=yes` - Isolated /tmp directory
- `NoNewPrivileges=yes` - Cannot escalate privileges
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=yes` - No access to user home directories

### Network Security

- Service binds to `0.0.0.0:11436` by default (all interfaces)
- **No authentication** by default (local network trust model)
- **For production:** Use reverse proxy (nginx) with authentication

## Error Handling

### Startup Failures

**Hailo device not found:**
```
Error: /dev/hailo0 not found
→ Solution: Install Hailo driver (sudo apt install dkms hailo-h10-all)
```

**Model not found:**
```
Error: Cannot load model 'yolov8s-pose.hef'
→ Solution: Download model or check model path
```

**Port already in use:**
```
Error: Address already in use (port 11436)
→ Solution: Change port in config or stop conflicting service
```

### Runtime Failures

**Inference timeout:**
- Retry with exponential backoff
- Log error to journald
- Return HTTP 500 with error details

**Memory allocation failure:**
- Log error
- Return HTTP 500
- Service continues (next request may succeed)

**Invalid image format:**
- Return HTTP 400
- Provide detailed error message
- Service continues normally

## Monitoring

### Health Checks

**systemd:**
```bash
systemctl status hailo-pose.service
```

**HTTP health endpoint:**
```bash
curl http://localhost:11436/health
```

**Readiness probe:**
```bash
curl http://localhost:11436/health/ready
```

### Logging

**journald integration:**
```bash
journalctl -u hailo-pose.service -f
```

**Log levels:**
- `INFO`: Startup, shutdown, config changes
- `WARNING`: Non-fatal errors, degraded performance
- `ERROR`: Fatal errors, inference failures

### Metrics

**TODO:** Expose Prometheus metrics endpoint
- Request count, latency histogram
- Inference time (preprocessing, NPU, postprocessing)
- Memory usage, CPU usage
- Error rates

## Testing Strategy

### Unit Tests

- Configuration loading/validation
- Request parsing (multipart, JSON, base64)
- Error handling

### Integration Tests

- Full inference pipeline with sample images
- Multi-person detection
- Edge cases (empty image, no persons detected)

### Performance Tests

- Latency benchmarks (p50, p95, p99)
- Throughput tests (sustained FPS)
- Memory leak detection (long-running stress test)

## Future Enhancements

### Model Support

- [ ] YOLOv8x-pose (larger, more accurate)
- [ ] Custom pose models (animal pose, hand pose)
- [ ] Multi-model serving (switch models per request)

### Features

- [ ] Video stream support (WebRTC or RTSP)
- [ ] Batch inference (multiple images per request)
- [ ] Tracking (person ID persistence across frames)
- [ ] Action recognition (classify poses: running, jumping, etc.)

### Operations

- [ ] Prometheus metrics
- [ ] Grafana dashboard
- [ ] Automatic model downloading
- [ ] Health check with model warm-up
- [ ] Graceful degradation (fallback to CPU if NPU fails)

## References

- YOLOv8 Architecture: https://docs.ultralytics.com/models/yolov8/
- COCO Keypoint Format: https://cocodataset.org/#keypoints-2020
- HailoRT SDK Documentation: https://hailo.ai/developer-zone/documentation/
- systemd Service Hardening: https://www.freedesktop.org/software/systemd/man/systemd.exec.html
