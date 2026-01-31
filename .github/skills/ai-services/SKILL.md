---
name: ai-services
description: Hailo-optimized AI service patterns and best practices
---

# Hailo AI Services Architecture

This skill provides pragmatic patterns for AI service APIs that leverage Hailo-10H on Raspberry Pi 5.

## Core Principle: Stand on Proven Shoulders

**Adopt existing standards:** Don't invent new APIs. Use proven protocols and conventions:
- **LLM inference:** Ollama API (adopted by thousands of projects)
- **Object detection:** Standard bbox JSON formats (COCO, YOLO conventions)
- **Pose estimation:** Standard keypoint formats (COCO pose, OpenPose conventions)
- **Speech/TTS:** Whisper API patterns, standard audio formats (WAV, MP3)
- **OCR:** Standard text detection/recognition formats
- **Depth estimation:** Standard depth map formats (PNG, NumPy arrays)
- **General REST:** Standard HTTP methods, JSON, conventional status codes
- **Health checks:** Simple `GET /health` or `/api/health`

Benefit: Works with existing client tools, familiar to users, reduces code to write and maintain.

*These are personal projects and art installations—reuse over reinvention.*

## Service Types from hailo-apps

The hailo-apps submodule provides **20+ AI applications** across vision and GenAI domains. Each can be wrapped as a systemd service.

**Architecture Note:** Hailo-10H supports **concurrent services** — multiple models can run simultaneously. Design services to:
- Load models at startup and keep them resident (startup latency ~10-30s is costly)
- Support graceful unload via API endpoint (for memory management)
- Budget memory across all active services (~5-6GB total available)

### LLM Inference (hailo-ollama) — Starting Point
**Purpose:** Expose LLM inference via Ollama API as a systemd service

**Pattern:**
- Ollama-compatible REST endpoints (`/api/tags`, `/api/chat`, `/api/generate`)
- Model lifecycle management, port 11434
- **Why first?** Ollama is the most widely adopted local LLM standard

### Computer Vision Services (from hailo-apps)

Available applications ready for service deployment:

**Object Detection:**
- YOLO (v5, v6, v8, v11), SSD, CenterNet variants
- Standard COCO bbox format output
- Potential API: `/api/detect` endpoint with image upload

**Pose Estimation:**
- YOLOv8 pose models (13+ keypoints per person)
- Standard COCO pose keypoint format
- Potential API: `/api/pose` endpoint returning joint coordinates

**Instance Segmentation:**
- YOLOv5/v8 segmentation models
- Per-instance pixel masks
- Potential API: `/api/segment` with mask output

**Depth Estimation:**
- Monocular (scdepthv3) and stereo (stereonet)
- Depth map output (PNG or NumPy)
- Potential API: `/api/depth` returning depth maps

**OCR:**
- PaddleOCR text detection + recognition
- Standard text/bbox JSON output
- Potential API: `/api/ocr` following Tesseract conventions

**Face Recognition:**
- Face detection + embedding comparison
- Standard face detection bbox format
- Potential API: `/api/faces` with recognition results

**Other Vision:**
- Object Detection services:**
```bash
curl -X POST http://localhost:8080/api/detect \
  -F "image=@photo.jpg" \
  -H "Content-Type: multipart/form-data"
# Returns COCO-format bboxes: [{"label": "person", "confidence": 0.95, "bbox": [x, y, w, h]}]
```

**Pose Estimation services:**
```bash
curl -X POST http://localhost:8081/api/pose \
  -F "image=@person.jpg"
# Returns keypoints: [{"person_id": 0, "keypoints": [{"name": "nose", "x": 120, "y": 80}...]}]
```

**Speech-to-Text services (Whisper API format):**
```bash
curl -X POST http://localhost:8082/api/transcribe \
  -F "audio=@speech.wav" \
  -F "language=en"
# Returns: {"text": "Hello world", "language": "en", "duration": 2.5}
```

**Text-to-Speech services (Piper TTS):**
```bash
curl -X POST http://localhost:8083/api/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "en_US-amy-low"}' \
  --output speech.wav
# Returns audio file (WAV format)
```

**General principles for all services:**
- Adopt the existing API standard for that AI domain (Ollama, Whisper, COCO, etc.)
- Use standard HTTP conventions (200 OK, 400 Bad Request, 404 Not Found, 503 Service Unavailable)
- JSON request/response bodies; multipart for file uploads
- Health check endpoint (e.g., `/api/health`, `/health`
- Potential API: `/api/transcribe` with audio upload

**Voice Assistant:**
- End-to-end speech → LLM → TTS pipeline
- WebSocket or streaming API
- Potential API: `/api/voice` streaming endpoint

**Vision-Language Models:**
- Image + text reasoning (VLM chat)
- Standard multimodal input format
- Potential API: `/api/vlm` with image + prompt

### Service Deployment Pattern

For each AI capability:
1. **Identify existing API standard** for that domain (if one exists)
2. **Wrap hailo-apps application** in REST API server
3. **Deploy as systemd service** with health checks
4. **Use Hailo-10 acceleration** where available
5. **Standard error handling** and logging to journald

### Batch Processing Service (Future)
**Purpose:** Queue-based inference for non-interactive workloads

**Characteristics:**
- Consume tasks from queue (file, message broker, API)
- Process in batches for efficiency
- Store results to database or file system
- Lower latency requirements than interactive API

## API Design Patterns

### Follow the Standard for Your Domain

**Ollama-based services (LLM):**
```bash
curl http://localhost:11434/api/tags  # Standard Ollama endpoint
```

**Object Detection services:**
```bash
curl -X POST http://localhost:8080/api/detect \
  -F "image=@photo.jpg" \
  -H "Content-Type: multipart/form-data"
# Returns COCO-format bboxes: [{"label": "person", "confidence": 0.95, "bbox": [x, y, w, h]}]
```

**Pose Estimation services:**
```bash
curl -X POST http://localhost:8081/api/pose \
  -F "image=@person.jpg"
# Returns keypoints: [{"person_id": 0, "keypoints": [{"name": "nose", "x": 120, "y": 80}...]}]
```

**Speech-to-Text services (Whisper API format):**
```bash
curl -X POST http://localhost:8082/api/transcribe \
  -F "audio=@speech.wav" \
  -F "language=en"
# Returns: {"text": "Hello world", "language": "en", "duration": 2.5}
```

**Text-to-Speech services (Piper TTS):**
```bash
curl -X POST http://localhost:8083/api/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "en_US-amy-low"}' \
  --output speech.wav
# Returns audio file (WAV format)
```

**General principles for all services:**
- Adopt the existing API standard for that AI domain (Ollama, Whisper, COCO, etc.)
- Use standard HTTP conventions (200 OK, 400 Bad Request, 404 Not Found, 503 Service Unavailable)
- JSON request/response bodies; multipart for file uploads
- Health check endpoint (e.g., `/api/health`, `/health`)

### Pragmatic Error Handling

Keep it simple:
```json
{
  "error": "Model not found",
  "detail": "Available models: neural-chat, mistral"
}
```

No need for custom error codes if standard HTTP status codes work.

### Async Request/Response (optional)

For long-running inference:

```
POST /api/infer
Body: {"model": "llama2", "prompt": "..."}
Response: {"job_id": "abc123", "status": "queued"}

GET /api/infer/abc123
Response: {"status": "complete", "result": "..."}
```

## Model Management

### Model Lifecycle Strategy

**Persistent Loading (Preferred):**
- Load models at service startup; keep resident in memory
- Avoids 10-30s startup latency on each inference request
- Suitable for services with regular usage patterns

**Graceful Unloading (When Needed):**
- Expose `/api/unload` endpoint to release model memory
- Useful for memory-constrained scenarios or infrequent usage
- Service should support reload on next inference request

**Concurrent Services:**
- Multiple services (e.g., LLM + STT + vision) can run simultaneously
- Total memory budget: ~5-6GB across all services
- Example allocation: Ollama 2GB + Whisper 1GB + YOLO 1GB + OS overhead

### Ollama Model Paths

```bash
# Default model storage
~hailo/.ollama/models/                 # User home
/var/lib/ollama/models/                # System service

# Model structure
/var/lib/ollama/models/manifests/<namespace>/<model>:<tag>
/var/lib/ollama/models/blobs/           # Actual model files
```

### Model Lifecycle API Patterns

**Recommended pattern for persistent services:**

```bash
# Service startup: Load model into memory (happens once)
# - Model remains resident until service stop or explicit unload
# - First inference after startup: ~10-30s (model loading)
# - Subsequent inferences: <1s (model already loaded)

# List loaded models
curl http://localhost:11434/api/tags
# Returns: {"models": [{"name": "llama2", "size": "4.1GB", "loaded": true}]}

# Inference (uses already-loaded model)
curl -X POST http://localhost:11434/api/chat -d '{"model": "llama2", "messages": [...]}'
# Fast response (model already in memory)

# Graceful unload (optional, for memory management)
curl -X POST http://localhost:11434/api/unload -d '{"model": "llama2"}'
# Releases memory; next inference will reload (slow)

# Health check includes model status
curl http://localhost:11434/api/health
# Returns: {"status": "ok", "models_loaded": ["llama2"], "memory_used_mb": 4200}
```

**Design principle:** Services should keep models loaded by default. Only unload when:
- User explicitly requests via `/api/unload` endpoint
- Memory pressure detected (optional: auto-unload least-recently-used)
- Service shutdown (graceful cleanup)

### Model Selection for Raspberry Pi

**Recommended models for single-service deployment:**
- `neural-chat` (7B, ~4GB) - Good for dedicated LLM service
- `mistral` (7B, ~4GB) - Faster inference, good general use
- `orca-mini` (3B, ~2GB) - Lowest memory, good for multi-service setups

**For concurrent multi-service scenarios:**
- Use smaller models to fit memory budget
- Example: `orca-mini` (2GB) + Whisper-tiny (512MB) + YOLO (512MB) = ~3GB total
- Monitor memory with: `free -h` and `/api/health` endpoints

**Avoid:**
- 13B+ models when running multiple services (exceed total RAM budget)
- Frequent model reloading (adds 10-30s latency each time)

## Resource Management

### Memory Budgeting

```
Total Pi 5 RAM:              8 GB
Reserved for OS:             1 GB
Available for services:      ~7 GB

Ollama process overhead:     ~300 MB
Model cache (llama2 7B):     ~5 GB
Inference workspace:         ~1 GB buffer
```

**Action:** Set `MemoryLimit=6G` in systemd unit to prevent swap thrashing.

### CPU Performance Considerations

```
Hailo-10 offloads:     Tensor operations (inference)
CPU still handles:     Tokenization, sampling, post-processing

Typical CPU load:      30-50% during active inference
Thermal idle:          35-45°C (with passive cooling)
Thermal active use:    50-65°C (with active fan)
```

**Action:** Monitor CPU usage in `journalctl` logs; if sustained >80%, reduce batch size or model size.

### Thermal Management

```bash
# Monitor service + system temperature
while true; do
  echo "$(date): $(vcgencmd measure_temp)"
  sleep 5
done

# Log thermal events to journalctl
# Modify service unit:
# ExecStartPost=/usr/local/bin/log-thermal-baseline.sh
```

**Throttle recovery:**
- If temperature >80°C: CPU governor reduces frequency
- Service may emit 503 errors during throttle
- Normal operation resumes as temperature drops
- Implement retry logic in clients

## Deployment Checklist

- [ ] Device access verified: `hailortcli fw-control identify`
- [ ] User/group created: `hailo:hailo`
- [ ] Device permissions set: `ls -l /dev/hailo0` shows `hailo` group
- [ ] Model storage directory created and owned by `hailo`
- [ ] systemd unit file installed and validated: `systemd-analyze verify`
- [ ] Service starts without errors: `systemctl start` + check logs
- [ ] Model loads at startup: Check logs for "Model loaded" confirmation
- [ ] Health check passes: `curl http://localhost:PORT/api/health`
- [ ] Model inference tested: `curl ... /api/chat` with sample request (fast response)
- [ ] Memory budget verified: `free -h` shows adequate headroom if running concurrent services
- [ ] Graceful unload tested (optional): `curl .../api/unload` releases memory
- [ ] Restart policy verified: Kill process, check auto-restart via `systemctl status`
- [ ] Logging configured: `journalctl -u service-name` shows activity

## Common Patterns

### Graceful Shutdown

```python
# Python service code
import signal

def signal_handler(sig, frame):
    print("Shutting down gracefully...")
    # Save model state, close Hailo device connection
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
```

```bash
# systemd unit
TimeoutStopSec=30
KillSignal=SIGTERM
```

### Dependency on System Setup

```bash
# In installer, verify prerequisites:
if ! command -v hailortcli &> /dev/null; then
    echo "ERROR: Hailo driver not installed. Run system setup first."
    exit 1
fi

if ! [ -e /dev/hailo0 ]; then
    echo "ERROR: /dev/hailo0 not found. Reboot after hailo-h10-all install."
    exit 1
fi
```

### Model Pre-caching

```bash
# Installer: Pre-download and load model to avoid cold-start delays
su - hailo -s /bin/bash -c "/usr/local/bin/ollama pull neural-chat"

# Service startup script loads model into memory:
# - systemd ExecStartPost can trigger initial model load
# - Or service startup code loads default model
# - Subsequent requests use already-loaded model (fast)
```

### Managing Multiple Concurrent Services

```bash
# Example multi-service deployment on Pi 5 (8GB RAM):
# - hailo-ollama: 2GB (LLM inference)
# - hailo-whisper: 1GB (STT)
# - hailo-yolo: 512MB (object detection)
# - OS + overhead: 1.5GB
# Total: ~5GB (safe with headroom)

# Monitor memory across services:
free -h
systemctl status hailo-ollama hailo-whisper hailo-yolo

# Each service tracks its own memory via /api/health:
curl http://localhost:11434/api/health  # Ollama
curl http://localhost:8082/api/health   # Whisper
curl http://localhost:8080/api/health   # YOLO
```

## Monitoring & Debugging

### systemd Service Logs

```bash
# Real-time logs
sudo journalctl -u hailo-ollama.service -f

# Debug level logs (if configured)
sudo journalctl -u hailo-ollama.service -p debug

# Continuous output with timestamps
sudo journalctl -u hailo-ollama.service -o short-iso -f
```

### API Testing

```bash
# Health
curl http://localhost:11434/api/health | jq

# List models
curl http://localhost:11434/api/tags | jq

# Chat inference
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "neural-chat",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }' | jq
```

### Thermal & Resource Monitoring

```bash
# During active inference, monitor in separate terminal
watch -n 1 'echo "Temp: $(vcgencmd measure_temp)" && \
  free -h && \
  ps aux | grep hailo-ollama'
```

---

**Reference:**
- Ollama API: https://github.com/ollama/ollama/blob/main/docs/api.md
- Hailo documentation: https://www.raspberrypi.com/documentation/computers/ai.html
