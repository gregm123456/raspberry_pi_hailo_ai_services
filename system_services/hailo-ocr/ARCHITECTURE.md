# Hailo OCR Service Architecture

## Purpose

Deploy PaddleOCR (text detection and recognition) as a managed systemd service on Raspberry Pi 5 + Hailo-10H, exposing a REST API at port 11436 for document scanning, text extraction, and OCR analysis with caching support.

## Constraints

- **Device access:** `/dev/hailo0` available but not directly used by PaddleOCR (CPU inference with optional ONNX runtime acceleration)
- **RAM budget:** ~1-2 GB for PaddleOCR models; total Pi 5 available is 5-6 GB
- **Thermals:** CPU throttles near 80°C; sustained OCR workloads may reduce throughput
- **Concurrency:** Can run alongside `hailo-ollama`, `hailo-vision` with proper memory budgeting
- **Model Loading:** Lazy load on first request (~2-3s); subsequent requests <<1s

## Components

```
systemd: hailo-ocr.service
 ├─ ExecStart: /usr/local/bin/hailo-ocr-server (or Python wrapper)
 ├─ User: hailo-ocr
 ├─ XDG_CONFIG_HOME=/etc/xdg
 ├─ XDG_DATA_HOME=/var/lib
 ├─ Config YAML: /etc/hailo/hailo-ocr.yaml
 ├─ Config JSON: /etc/xdg/hailo-ocr/hailo-ocr.json
 └─ Data dir: /var/lib/hailo-ocr
     ├─ models/
     ├─ cache/
     └─ temp/
```

## Service Architecture

### 1. Process Model

**Type:** `simple` (Python asyncio server with signal handling)

The service runs a long-lived Python asyncio process that:
- Initializes PaddleOCR models on startup (lazy load on first request)
- Maintains object cache for prior OCR results
- Exposes REST endpoints via `aiohttp` or `fastapi`
- Logs to journald via `logging` module

**Startup Flow:**
1. Service reads config from `/etc/xdg/hailo-ocr/hailo-ocr.json`
2. Initializes asyncio event loop and HTTP server
3. Binds to configured port (default 11436)
4. Signals readiness; first OCR request triggers model load (~2-3s)
5. Responds to subsequent requests with cached models

**Shutdown Flow:**
1. Systemd sends `SIGTERM` on stop
2. Service stops accepting new requests
3. Flushes caches gracefully
4. Exits cleanly within 30s timeout

### 2. Configuration Flow

**YAML → JSON Pipeline:**
1. Operator edits `/etc/hailo/hailo-ocr.yaml` (user-friendly)
2. `render_config.py` converts YAML to `/etc/xdg/hailo-ocr/hailo-ocr.json` (schema validated)
3. Service reads JSON on startup
4. Updates applied by restarting service: `sudo systemctl restart hailo-ocr`

**Config Versioning:**
- YAML is source of truth (checked into version control)
- JSON is generated, not committed
- Allows deployment-specific overrides

### 3. Model Lifecycle

**Lazy Loading (Recommended):**
```
[Service Start (fast)]
    ↓
[Ready for connections]
    ↓
[First OCR Request]
    ↓
[Load Detection Model] (~1-2s)
    ↓
[Load Recognition Model] (~1s)
    ↓
[Process Image] (~100-500ms)
    ↓
[Requests 2, 3, 4, ...] (each ~100-500ms)
    ↓
[Service Stop]
    ↓
[Unload Models]
    ↓
[Exit]
```

**Pre-loaded Alternative (slower startup, faster first request):**
- Load models during service initialization
- Trade: ~3-4s startup time for immediate ~200ms first request
- Not default; can be enabled via `--preload-models` flag in install.sh

**Current Implementation:** Lazy loading (optimal for responsive startup).

### 4. Memory Budgeting

| Component | Typical Memory | Notes |
|-----------|---|---|
| Detection model (PP-OCR) | 100-200 MB | DNN weights + runtime cache |
| Recognition model (PP-OCR-V3) | 800 MB - 1.2 GB | Large character set model |
| Python runtime + deps | 200-300 MB | asyncio, numpy, PIL |
| Result cache (in-memory) | 100-500 MB | Configurable TTL |
| Processing workspace | 200-400 MB | Temporary image buffers |
| **Total (loaded)** | **1.5-2.5 GB** | Conservative estimate with cache |

**Concurrent Services (Pi 5 with 8GB):**
- hailo-ocr: 2.0 GB
- hailo-ollama: 3.0 GB
- hailo-vision: 3.0 GB
- System/buffer: 0.5 GB
- **Total:** ~8.5 GB (at capacity; monitor for OOM)

If multiple services run together, monitor via `free -h` and `journalctl -u systemd-oomkill`.

### 5. API Endpoints

**Public API (port 11436):**
- `GET /health` — Service status + memory usage
- `GET /health/ready` — Readiness probe (returns 503 if loading)
- `GET /models` — List available OCR languages
- `POST /v1/ocr/extract` — Single-image OCR
- `POST /v1/ocr/batch` — Batch multi-image OCR
- `POST /v1/ocr/analyze` — Advanced analysis (layout detection, etc.)
- `DELETE /cache` — Clear result cache

**Logging:**
- All requests logged to stdout (captured by systemd journald)
- Processing times logged for performance monitoring
- Errors logged with context and stack traces

### 6. Caching Strategy

**In-Memory Result Cache:**
- Stores OCR results by image hash (MD5)
- TTL configurable (default 3600s = 1 hour)
- LRU eviction if cache exceeds size limit (default 500 MB)
- Disabled by default (can enable via config)

**Use Cases:**
- Repeated document scanning (e.g., same page submitted twice)
- Batch processing with duplicate images
- Performance testing

### 7. Device Access & Permissions

**Setup:**
```bash
# Service user created without device access (PaddleOCR is CPU-based)
useradd -r -s /usr/sbin/nologin hailo-ocr
```

**Verification:**
```bash
su - hailo-ocr -s /bin/bash
# Verify disk access to /var/lib/hailo-ocr
ls -la /var/lib/hailo-ocr/
```

### 8. systemd Unit Configuration

**Key Directives:**

| Directive | Value | Reason |
|-----------|---|---|
| `Type` | `simple` | Long-lived asyncio process |
| `Restart` | `always` | Auto-restart on crash |
| `RestartSec` | `5` | 5s delay before restart attempt |
| `TimeoutStopSec` | `30` | Wait up to 30s for graceful shutdown |
| `KillSignal` | `SIGTERM` | Allow signal handler cleanup |
| `MemoryMax` | `2.5G` | Hard limit on memory usage |
| `CPUQuota` | `75%` | Prevent 100% CPU-throttle cycle |
| `PrivateTmp` | `yes` | Isolate temp files |
| `NoNewPrivileges` | `yes` | Security hardening |

**Environment Variables:**
```bash
XDG_CONFIG_HOME=/etc/xdg
XDG_DATA_HOME=/var/lib
PYTHONUNBUFFERED=1  # Real-time logging
```

### 9. Error Handling & Recovery

**Startup Failures:**
- Config file missing → Use defaults, log warning
- Model download fails (no internet) → Exit with error, systemd auto-restarts
- Port already in use → Exit with error (fix via config)

**Runtime Failures:**
- OOM killer → systemd logs event, service restarts
- Input image too large → Return 413 (Payload Too Large)
- Invalid image format → Return 400 (Bad Request)
- OCR model crash → Restart on next request (Restart=always)

**Health Checks:**
- Systemd auto-restarts on `Restart=always` on failure
- Manual health check: `curl http://localhost:11436/health`
- Readiness probe: `curl http://localhost:11436/health/ready` (returns 503 if loading)

### 10. Logging & Observability

**Logs routed to journald:**
```bash
sudo journalctl -u hailo-ocr.service -f        # Follow real-time logs
sudo journalctl -u hailo-ocr.service -n 100    # Last 100 lines
sudo journalctl -u hailo-ocr.service -p err   # Errors only
```

**Log Fields:**
- Timestamp
- Service name + PID
- Message level (INFO, WARNING, ERROR)
- Request ID (for tracing)
- Processing time (detection + recognition)

**Performance Metrics Logged:**
```
[INFO] request_id=ocr-abc123 endpoint=/v1/ocr/extract method=POST
[INFO] image_size=1920x1080 format=jpeg languages=["en"]
[INFO] detection_time_ms=150 recognition_time_ms=200 total_ms=350
[INFO] text_regions_found=12 avg_confidence=0.92
```

### 11. Known Limitations

1. **Single Language:** Detects text in specified languages; requires config update to add more
2. **Image Size:** Maximum 4096×4096 pixels (configurable); larger images rejected
3. **Languages:** Typical 2-3 languages per service (download size ~500 MB each)
4. **No Authentication:** API is open; assumes private network or firewall
5. **No Rate Limiting:** Implemented at deployment layer if needed (e.g., nginx)
6. **Cache Persistence:** Results stored in-memory only; lost on restart

### 12. Future Improvements

- **Language-specific Model Switching:** Support loading alternative models at runtime
- **Batch Parallel Processing:** Process multiple images concurrently
- **Persistent Result Cache:** SQLite-backed cache for OCR results across restarts
- **Layout Analysis:** Detect page layout (headings, paragraphs, tables)
- **Handwriting Support:** Integrate handwritten text recognition model
- **TLS Termination:** Optional reverse proxy (nginx) for HTTPS
- **Metrics Export:** Prometheus-compatible `/metrics` endpoint
- **GPU Acceleration:** Optional CUDA/OpenVINO support (if Pi 5 supports in future)

### 13. Resource Monitoring

**Memory Usage:**
```bash
ps aux | grep hailo-ocr
# Check RSS (resident set size)
```

**Processing Performance:**
```bash
# Monitor via logs
journalctl -u hailo-ocr.service | grep "total_ms"
```

**System Load:**
```bash
top -p $(pgrep -f hailo-ocr)              # Process CPU/memory
free -h                                    # System memory
vcgencmd measure_temp                      # Thermal status (RPi)
```

### 14. Integration Notes

- **Hailo Device:** Not directly used; PaddleOCR uses CPU. Can share /dev/hailo0 with other services.
- **Model Storage:** All models stored in `/var/lib/hailo-ocr/models/` (~500 MB per language)
- **Idempotent Config:** Multiple config updates safe; just restart service
- **Horizontal Scaling:** Can run multiple OCR services on same Pi with different ports (11436, 11437, etc.)
