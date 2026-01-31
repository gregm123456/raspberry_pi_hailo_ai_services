# Hailo Depth Estimation Service Architecture

Design and implementation details for the `hailo-depth` system service.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Hailo Depth Service                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────┐         ┌──────────────┐               │
│  │  REST API     │────────▶│  Depth       │               │
│  │  (aiohttp)    │         │  Estimator   │               │
│  │               │◀────────│              │               │
│  └───────────────┘         └──────┬───────┘               │
│         │                          │                       │
│         │                          ▼                       │
│         │                  ┌──────────────┐               │
│         │                  │  HailoRT SDK │               │
│         │                  │              │               │
│         │                  └──────┬───────┘               │
│         │                          │                       │
│         ▼                          ▼                       │
│  ┌────────────┐            ┌─────────────┐               │
│  │  Config    │            │  /dev/hailo0│               │
│  │  (JSON)    │            │  (NPU)      │               │
│  └────────────┘            └─────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                                  │
         ▼                                  ▼
   journald logs                    /var/lib/hailo-depth/
```

---

## Components

### 1. REST API Layer

**Technology:** aiohttp (asyncio-based HTTP server)

**Responsibilities:**
- Accept HTTP requests (multipart or JSON)
- Parse and validate input images
- Handle authentication (future)
- Format responses (JSON)
- Error handling and logging

**Endpoints:**
- `GET /health` - Service health check
- `GET /health/ready` - Readiness probe
- `GET /v1/info` - Service information
- `POST /v1/depth/estimate` - Depth estimation inference

**Port:** 11436 (configurable)

**Concurrency:** Single-threaded async I/O (handles multiple connections, one inference at a time)

---

### 2. Depth Estimator

**Responsibilities:**
- Model lifecycle management (load/unload)
- Image preprocessing (resize, normalize)
- HailoRT inference execution
- Postprocessing (depth map extraction, normalization)
- Output encoding (NumPy NPZ, PNG visualization)

**Model Loading:**
- **Startup:** Load model at service initialization
- **Keep-Alive:** Model stays resident in memory (default: `-1` = persistent)
- **Unload:** Graceful shutdown on service stop

**Inference Pipeline:**
1. Decode input image (PIL)
2. Preprocess (resize to model input size, format conversion)
3. Copy to HailoRT input tensor
4. Run inference on NPU via `/dev/hailo0`
5. Read output tensor (depth map)
6. Postprocess (denormalize, apply colormap if requested)
7. Encode output (NPZ, PNG)

---

### 3. HailoRT SDK Integration

**Purpose:** Interface with Hailo-10H NPU for model execution.

**Key Operations:**
- Device initialization (`/dev/hailo0`)
- HEF (Hailo Executable Format) loading
- Tensor allocation and copy
- Inference execution
- Result retrieval

**Model:** `scdepthv3.hef` (SCDepthV3 monocular depth estimation)

**Expected Location:**
- HEF files: `/var/lib/hailo-depth/models/`
- Post-processing libraries: `/usr/lib/hailo-apps-infra/`

**Device Access:**
- User `hailo-depth` is added to the Hailo device group (typically `hailo`)
- Service has read/write access to `/dev/hailo0`

---

### 4. Configuration Management

**Config Files:**
- **YAML Source:** `/etc/hailo/hailo-depth.yaml` (human-editable)
- **JSON Runtime:** `/etc/xdg/hailo-depth/hailo-depth.json` (parsed by service)

**Rendering:** `render_config.py` converts YAML to JSON at install time.

**Configuration Sections:**

```yaml
server:
  host: 0.0.0.0
  port: 11436

model:
  name: "scdepthv3"
  type: "monocular"
  keep_alive: -1

output:
  format: "both"
  colormap: "viridis"
  normalize: true

resource_limits:
  memory_max: "3G"
  cpu_quota: "80%"
```

**Reload:** Requires service restart after config changes.

---

### 5. systemd Integration

**Unit File:** `/etc/systemd/system/hailo-depth.service`

**Type:** `simple` (foreground service)

**User/Group:** `hailo-depth` (non-privileged)

**Dependencies:**
- `After=network-online.target` - Wait for network
- `Wants=network-online.target` - Network is desired

**Environment Variables:**
- `XDG_CONFIG_HOME=/etc/xdg` - Config directory
- `HAILO_PRINT_TO_SYSLOG=1` - HailoRT logs to journald
- `PYTHONUNBUFFERED=1` - Real-time Python logging

**Restart Policy:**
- `Restart=always` - Auto-restart on failure
- `RestartSec=5` - 5-second delay between restarts
- `TimeoutStopSec=30` - 30-second graceful shutdown timeout

**Resource Limits:**
- `MemoryMax=3G` - Maximum memory usage
- `CPUQuota=80%` - CPU cap (4 out of 5 cores on Pi 5)

**Security:**
- `PrivateTmp=yes` - Isolated /tmp
- `NoNewPrivileges=yes` - Prevent privilege escalation
- `ProtectSystem=strict` - Read-only filesystem (except allowed paths)
- `ProtectHome=yes` - No access to user home directories

---

## Model Lifecycle

### Persistent Loading (Default)

```
Service Start
     │
     ├─► Load Model (HEF)
     │      │
     │      ├─► Initialize NPU
     │      ├─► Allocate Tensors
     │      └─► Mark as Ready
     │
     ├─► Start HTTP Server
     │
     ├─► Accept Requests
     │      │
     │      ├─► Request 1 (inference)
     │      ├─► Request 2 (inference)
     │      └─► Request N (inference)
     │
     └─► Service Stop
            └─► Unload Model
                └─► Shutdown
```

**Advantages:**
- Low latency (no model loading per request)
- Predictable performance
- Suitable for continuous operation

**Trade-offs:**
- Higher memory usage
- Model stays resident even when idle

### On-Demand Loading (Alternative)

Set `model.keep_alive: 0` in config.

```
Request
   │
   ├─► Check if Model Loaded
   │      │
   │      ├─► No: Load Model (add latency)
   │      └─► Yes: Use Loaded Model
   │
   ├─► Run Inference
   │
   └─► Unload Model Immediately
```

**Advantages:**
- Lower idle memory usage
- Model memory available for other services

**Trade-offs:**
- Higher latency (model loading per request)
- Increased NPU device contention

---

## Resource Management

### Memory Budget

**Breakdown (SCDepthV3):**
- Model weights: ~150-200 MB
- Inference tensors: ~50-100 MB
- Python runtime: ~100-200 MB
- Image buffers: ~50 MB
- Overhead: ~100 MB
- **Total:** ~500-650 MB typical, **3GB max limit**

**Concurrent Services:**
- hailo-depth: 3GB
- hailo-vision: 4GB
- hailo-ollama: N/A (separate LLM)
- Total Pi 5 RAM: ~8GB (OS + services)

**Recommendation:** Run 2-3 AI services concurrently; monitor with `systemd-cgtop`.

### CPU Allocation

**Limit:** 80% CPU quota (4 out of 5 cores on Pi 5)

**Rationale:**
- Preprocessing (image decode, resize): ~20-30% CPU
- Postprocessing (colormap, encoding): ~10-20% CPU
- Inference: Offloaded to NPU (minimal CPU)
- Reserve 20% for OS and other services

### Thermal Management

**Passive Cooling:** Recommended for sustained operation

**Monitor:** `vcgencmd measure_temp` or `/sys/class/thermal/thermal_zone0/temp`

**Thermal Throttling:**
- Pi 5 throttles at ~85°C
- Consider reducing CPU quota or adding active cooling if sustained high load

---

## Data Flow

### Request Processing

```
1. Client
   └─► HTTP POST /v1/depth/estimate
         │
         ▼
2. APIHandler.estimate()
   ├─► Parse multipart/JSON
   ├─► Decode image (base64 if JSON)
   ├─► Validate parameters
   └─► Call DepthEstimator.estimate_depth()
         │
         ▼
3. DepthEstimator.estimate_depth()
   ├─► Load image (PIL)
   ├─► Preprocess (resize, normalize)
   ├─► Run HailoRT inference
   │     └─► NPU execution via /dev/hailo0
   ├─► Postprocess (depth map)
   ├─► Normalize (optional)
   ├─► Encode NumPy (optional)
   ├─► Colorize PNG (optional)
   └─► Return result dict
         │
         ▼
4. APIHandler.estimate()
   ├─► Format JSON response
   └─► Send to client
         │
         ▼
5. Client
   └─► Receives JSON with depth_map/depth_image
```

---

## Security

### User Isolation

- Service runs as `hailo-depth:hailo-depth` (non-root)
- No shell access (`/usr/sbin/nologin`)
- Limited filesystem access (systemd sandboxing)

### Device Permissions

- User added to Hailo device group (read/write `/dev/hailo0`)
- No other privileged device access

### Network Exposure

- Default: Listen on all interfaces (`0.0.0.0:11436`)
- Recommendation: Use firewall or bind to `127.0.0.1` for localhost-only
- No TLS/HTTPS (add reverse proxy for production)

### Input Validation

- Image size limit: 50MB (configurable in `create_app()`)
- Format validation: PIL checks for valid image formats
- Malformed JSON: Rejected with 400 error

---

## Logging

### Destinations

- **journald:** All application logs via systemd
- **HailoRT:** NPU logs via `HAILO_PRINT_TO_SYSLOG=1`

### Log Levels

- `INFO`: Startup, shutdown, request summary
- `WARNING`: Non-fatal issues (health check failure, config warnings)
- `ERROR`: Request failures, model errors

### Access

```bash
# Service logs
sudo journalctl -u hailo-depth.service -f

# Recent errors
sudo journalctl -u hailo-depth.service -p err -n 50

# Follow with filtering
sudo journalctl -u hailo-depth.service -f --grep="inference"
```

---

## Performance Characteristics

### Inference Time

**SCDepthV3 (640x480 input):**
- NPU inference: ~30-40ms
- Preprocessing: ~5-10ms
- Postprocessing: ~5-10ms
- **Total:** ~40-60ms per request

**Factors:**
- Input image size (larger = more preprocessing)
- Output format (NumPy < Image < Both)
- Colormap rendering (Image output)

### Throughput

- **Sequential:** ~16-20 requests/second (single-threaded)
- **Concurrent:** N/A (inference serialized, NPU single-user)

### Latency Breakdown

```
Request Received
     │  (network)
     ▼
Parse & Decode (~1-5ms)
     │
     ▼
Preprocess (~5-10ms)
     │
     ▼
NPU Inference (~30-40ms)
     │
     ▼
Postprocess (~5-10ms)
     │
     ▼
Encode & Send (~1-5ms)
     │  (network)
     ▼
Response Received

Total: ~42-70ms
```

---

## Failure Modes

### Model Loading Failure

**Cause:** Missing HEF, corrupted file, NPU unavailable

**Behavior:** Service fails to start, exits with error

**Recovery:** Fix issue, restart service

### Inference Failure

**Cause:** Invalid input, memory exhaustion, NPU timeout

**Behavior:** Request returns 500 error, service continues

**Recovery:** Automatic (per-request error)

### NPU Device Unavailable

**Cause:** Driver not loaded, device in use, hardware failure

**Behavior:** Service fails to initialize

**Recovery:** Check `/dev/hailo0`, reload driver, reboot

### Memory Exhaustion

**Cause:** Memory leak, resource limit exceeded

**Behavior:** systemd OOM kill, service restart

**Recovery:** Automatic restart (systemd), investigate logs

---

## Future Enhancements

### Stereo Depth Estimation

- Add stereo models (e.g., StereoDepth)
- Support dual camera input
- API: `model.type: "stereo"`, two-image input

### Batch Inference

- Process multiple images in one request
- Amortize model loading overhead
- Higher throughput

### Streaming Video

- WebSocket or WebRTC for real-time depth
- Video pipeline integration
- Lower latency for continuous streams

### Model Switching

- Support multiple depth models
- Dynamic model selection per request
- API: `model` parameter in request

### Calibration

- Scene-specific depth calibration
- Absolute distance estimation (with known scale)
- Camera intrinsics integration

---

## References

- **SCDepthV3:** [arxiv.org/abs/2211.03660](https://arxiv.org/abs/2211.03660)
- **Hailo Model Zoo:** [github.com/hailo-ai/hailo_model_zoo](https://github.com/hailo-ai/hailo_model_zoo)
- **HailoRT SDK:** Hailo Developer Zone
- **systemd:** [systemd.io](https://systemd.io)
- **aiohttp:** [docs.aiohttp.org](https://docs.aiohttp.org)
