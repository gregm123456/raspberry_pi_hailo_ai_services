# Hailo Vision Service Architecture

## Purpose

Deploy Qwen2-VL-2B (Vision Language Model) as a managed systemd service on Raspberry Pi 5 + Hailo-10H, exposing a chat-based OpenAI-compatible API at port 11435 for multimodal image-text analysis.

## Constraints

- **Device access:** `/dev/hailo0` must be present and accessible by the service user.
- **RAM budget:** ~2–4 GB for the vision model; total Pi 5 available is 5–6 GB. Assume 4 GB reserved for system + LLM service if running concurrently.
- **Thermals:** CPU throttles near 80°C; sustained inference may reduce throughput. Expect ~1–2s latency under thermal load.
- **Concurrency:** Can run alongside `hailo-ollama` or other Hailo services with proper memory budgeting.
- **Model Loading:** Persistent loading (warm start) recommended for interactive use; ~1–2s load time on first request if unloaded.

## Components

```
systemd: hailo-vision.service
 ├─ ExecStart: /usr/local/bin/hailo-vision-server (or Python wrapper)
 ├─ User: hailo-vision
 ├─ XDG_CONFIG_HOME=/etc/xdg
 ├─ XDG_DATA_HOME=/var/lib
 ├─ Config JSON: /etc/xdg/hailo-vision/hailo-vision.json
 └─ Data dir: /var/lib/hailo-vision
     ├─ models/
     └─ cache/
```

## Service Architecture

### 1. Process Model

**Type:** `simple` (Python asyncio server with signal handling)

The service runs a long-lived Python asyncio process that:
- Initializes the Qwen VLM model on startup (warm load)
- Maintains the model in memory across requests
- Exposes REST endpoints via `aiohttp` or `fastapi`
- Logs to journald via `journalctl`

**Startup Flow:**
1. Service reads config from `/etc/xdg/hailo-vision/hailo-vision.json`
2. Opens `/dev/hailo0` device (requires `hailo-vision` user to have permissions)
3. Loads Qwen VLM model into NPU memory
4. Binds to configured port (default 11435)
5. Signals readiness via log output or systemd notify

**Shutdown Flow:**
1. Systemd sends `SIGTERM` on stop
2. Service stops accepting new requests
3. Gracefully unloads model
4. Exits cleanly within 30s timeout

### 2. Configuration Flow

**YAML → JSON Pipeline:**
1. Operator edits `/etc/hailo/hailo-vision.yaml` (user-friendly)
2. `render_config.py` converts YAML to `/etc/xdg/hailo-vision/hailo-vision.json` (schema validated)
3. Service reads JSON on startup
4. Updates applied by restarting service: `sudo systemctl restart hailo-vision`

**Config Versioning:**
- YAML is source of truth (checked into version control)
- JSON is generated, not committed
- Allows config to track deployment-specific overrides

### 3. Model Lifecycle

**Persistent Loading (Recommended):**
```
[Service Start]
    ↓
[Load Model to NPU] (~1–2s, happens once)
    ↓
[Ready to accept requests]
    ↓
[Requests 1, 2, 3, ...] (each ~200–600ms)
    ↓
[Service Stop]
    ↓
[Unload Model]
    ↓
[Exit]
```

**Alternative: On-Demand Loading (slower, saves memory):**
- Load model on first request after timeout
- Unload after idle period
- Trade: slower first response (~2–3s) for per-request memory savings
- Not recommended for interactive use

**Current Implementation:** Persistent loading (simplifies API, ensures responsiveness).

### 4. Memory Budgeting

| Component | VRAM | Notes |
|-----------|------|-------|
| Qwen2-VL-2B model | 2.0–3.0 GB | Primary allocation; main NPU memory |
| Python runtime + weights cache | 0.5–1.0 GB | System + metadata |
| Inference workspace | 0.5–1.0 GB | Temporary tensors during forward pass |
| **Total** | **3.0–4.0 GB** | ~4 GB recommended MemoryMax |

**Concurrent Services (Pi 5 with 8GB):**
- hailo-vision: 4.0 GB
- hailo-ollama: 3.0 GB
- System/buffer: 1.0 GB
- **Total:** ~8.0 GB (at capacity; monitor for OOM)

If both services run together, monitor via `free -h` and `journalctl -u systemd-oomkill`.

### 5. API Endpoints

**Public API (port 11435):**
- `GET /health` — Service status + memory usage
- `GET /health/ready` — Readiness probe (returns 503 if loading)
- `GET /v1/models` — List available models
- `POST /v1/chat/completions` — Vision chat (OpenAI-compatible)
- `POST /v1/vision/analyze` — Batch analysis (proprietary)

**Logging:**
- All requests logged to stdout (captured by systemd journald)
- Response times logged for performance monitoring
- Errors logged with full context and stack traces

### 6. Device Access & Permissions

**Setup:**
```bash
# Device group ownership (auto-detected by installer)
ls -l /dev/hailo0
# brw-rw---- 1 root hailo-devices 511, 0 Jan 31 10:00 /dev/hailo0

# Service user created and added to hailo-devices group
useradd -r -g hailo-devices hailo-vision
```

**Verification:**
```bash
su - hailo-vision -s /bin/bash
ls -l /dev/hailo0  # Should be readable/writable
```

### 7. systemd Unit Configuration

**Key Directives:**

| Directive | Value | Reason |
|-----------|-------|--------|
| `Type` | `simple` | Long-lived blocking process |
| `Restart` | `always` | Auto-restart on crash |
| `RestartSec` | `5` | 5s delay before restart attempt |
| `TimeoutStopSec` | `30` | Wait up to 30s for graceful shutdown |
| `KillSignal` | `SIGTERM` | Allow signal handler cleanup |
| `MemoryMax` | `4G` | Hard limit on VRAM usage |
| `CPUQuota` | `80%` | Prevent 100% CPU-throttle cycle |
| `PrivateTmp` | `yes` | Isolate temp files |
| `NoNewPrivileges` | `yes` | Security hardening |

**Environment Variables:**
```bash
XDG_CONFIG_HOME=/etc/xdg
XDG_DATA_HOME=/var/lib
HAILO_PRINT_TO_SYSLOG=1  # Log to journald
```

### 8. Error Handling & Recovery

**Startup Failures:**
- Device not found (`/dev/hailo0` missing) → Immediate exit with error
- Model load timeout (>10s) → Kill process, restart via Restart=always
- Port already in use → Exit with error (fix via config)

**Runtime Failures:**
- OOM killer → systemd logs event, service restarts
- Device disconnected → Graceful error response (503), log warning
- Invalid image → Return 400 with validation error

**Health Checks:**
- Systemd auto-restarts on `Restart=always` on failure
- Manual health check: `curl http://localhost:11435/health`
- Readiness probe: `curl http://localhost:11435/health/ready` (returns 503 if loading)

### 9. Logging & Observability

**Logs routed to journald:**
```bash
sudo journalctl -u hailo-vision.service -f        # Follow real-time logs
sudo journalctl -u hailo-vision.service -n 100    # Last 100 lines
sudo journalctl -u hailo-vision.service -p err    # Errors only
```

**Log Fields:**
- Timestamp
- Service name + PID
- Message level (INFO, WARNING, ERROR)
- Request ID (for tracing)
- Inference latency / throughput (for monitoring)

**Performance Metrics Logged:**
```
[INFO] request_id=abc123 endpoint=/v1/chat/completions method=POST
[INFO] inference_time_ms=450 load_time_ms=0 total_ms=455 model=qwen2-vl-2b tokens_generated=62
[INFO] image_size=1920x1080 prompt_tokens=256 completion_tokens=62
```

### 10. Known Limitations

1. **Single Model:** Only Qwen2-VL-2B-Instruct supported (extensible to other VLMs)
2. **Image Size:** Maximum 8 MP (typical: 3840×2160); larger images rejected with 400 error
3. **Token Limits:** Max 512 generation tokens (configurable)
4. **No Multi-GPU:** Single device inference only (/dev/hailo0)
5. **No Authentication:** API is open; assumes private network or firewall
6. **No Rate Limiting:** Implemented at deployment layer if needed (e.g., nginx)

### 11. Future Improvements

- **Model Switching:** Support multiple VLM variants at runtime (config-based)
- **TLS Termination:** Optional reverse proxy (nginx) for HTTPS
- **Token Caching:** Implement KV-cache for multi-turn conversations
- **Batch Inference:** Parallel processing of multiple requests
- **Metrics Export:** Prometheus-compatible `/metrics` endpoint
- **Performance Tuning:** Quantization options (int8, int4) for lower memory
- **Streaming Responses:** Token-by-token streaming for realtime UX

### 12. Resource Monitoring

**Memory Usage:**
```bash
ps aux | grep hailo-vision
# Check RSS (resident set size) vs VIRT (virtual)
```

**Device Utilization:**
```bash
watch -n 1 'hailortcli fw-control identify'  # Device health
vcgencmd measure_temp                         # Thermal status
```

**System Load:**
```bash
top -p $(pgrep -f hailo-vision)              # Process CPU/memory
free -h                                       # System memory
```
