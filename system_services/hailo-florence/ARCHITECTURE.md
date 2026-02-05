# hailo-florence Architecture

**Design Document for Florence-2 Image Captioning + VQA System Service**

---

## Overview

The `hailo-florence` service provides REST API access to Microsoft's Florence-2 vision-language model for automatic image captioning and visual question answering (VQA). It follows the established architecture pattern for Hailo system services: persistent model loading, systemd lifecycle management, and RESTful API exposure.

**Key Design Principles:**
1. **Model Persistence:** Load Florence-2 at startup, keep resident in memory
2. **Resource Budget:** Targeted 2-3 GB VRAM, ~3.5 GB total memory
3. **API Simplicity:** Two focused endpoints (`/v1/caption`, `/v1/vqa`) for description and Q&A
4. **Pragmatic Approach:** Build atop existing implementation in hailo-rpi5-examples
5. **systemd Integration:** Managed lifecycle, journald logging, health monitoring

---

## System Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                      │
│         (curl, Python scripts, web apps, etc.)              │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP REST API
                         │ POST /v1/caption
                         │ POST /v1/vqa
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  hailo-florence Service                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              FastAPI REST Server                      │  │
│  │  - Request validation & routing                       │  │
│  │  - Base64 image decoding                             │  │
│  │  - Response formatting                               │  │
│  └────────────────┬──────────────────────────────────────┘  │
│                   │                                          │
│  ┌────────────────▼──────────────────────────────────────┐  │
│  │         Florence-2 Inference Pipeline                 │  │
│  │  ┌────────────────┐  ┌──────────────┐               │  │
│  │  │ Vision Encoder │  │ Text Encoder │               │  │
│  │  │    (DaViT)     │  │   (BERT)     │               │  │
│  │  │    ONNX CPU    │  │  Hailo-10H   │               │  │
│  │  └────────┬───────┘  └──────┬───────┘               │  │
│  │           │                  │                        │  │
│  │           └────────┬─────────┘                        │  │
│  │                    ▼                                  │  │
│  │         ┌──────────────────────┐                     │  │
│  │         │  Decoder Transformer │                     │  │
│  │         │     Hailo-10H        │                     │  │
│  │         └──────────┬───────────┘                     │  │
│  │                    │                                  │  │
│  │                    ▼                                  │  │
│  │         ┌──────────────────────┐                     │  │
│  │         │   HF Tokenizer       │                     │  │
│  │         │   (decode tokens)    │                     │  │
│  │         └──────────────────────┘                     │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Hailo-10H NPU (/dev/hailo0)                    │
│  - Text encoder inference                                   │
│  - Decoder transformer inference                            │
│  - PCIe Gen 3 x4 communication                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. REST API Server (FastAPI)

**Purpose:** HTTP request handling and API exposure

**Implementation:**
- **Framework:** FastAPI (async-capable, auto-validation)
- **Port:** 11438 (default, configurable)
- **Workers:** Single-worker (no concurrent inference)
- **Endpoints:**
   - `POST /v1/caption` - Generate caption
   - `POST /v1/vqa` - Answer a question about an image
   - `GET /health` - Service health check
   - `GET /metrics` - Performance metrics

**Request Flow:**
1. Receive POST request with base64-encoded image
2. Validate image format and size
3. Decode base64 → PIL Image
4. Pass to Florence-2 pipeline
5. Format response with caption + metadata
6. Return JSON response

**Error Handling:**
- 400: Invalid image format or encoding
- 413: Image too large (>10 MB)
- 422: Invalid parameters (max_length, etc.)
- 500: Inference failure
- 503: Model not ready or Hailo device unavailable
- 501: VQA embedding missing (VQA not configured)

### 2. Florence-2 Inference Pipeline

**Based on:** `hailo-rpi5-examples/community_projects/dynamic_captioning/caption.py`

**Architecture:**
Florence-2 is a unified vision-language model with encoder-decoder architecture:

1. **Vision Encoder (DaViT - Dual Attention ViT)**
   - Input: 384x384 RGB image
   - Processing: ONNX runtime on CPU
   - Output: 2D visual feature map
   - Memory: ~500 MB
   - Latency: ~200-300ms

2. **Text Encoder (BERT-style)**
   - Input: Tokenized prompt (always `<task>`)
   - Processing: Hailo-10H NPU
   - Output: Contextual embeddings
   - Memory: ~500 MB
   - Latency: ~50ms

3. **Decoder Transformer**
   - Input: Visual features + text embeddings
   - Processing: Hailo-10H NPU
   - Output: Token sequence
   - Memory: ~1.5-2 GB
   - Latency: ~250-400ms (autoregressive)
   - Architecture: Transformer decoder with cross-attention

4. **Tokenizer (HuggingFace)**
   - Converts token IDs → text string
   - CPU processing
   - Latency: <10ms

**Model Files:**
- `vision_encoder.onnx` - Vision encoder (ONNX)
- `florence2_transformer_encoder.hef` - Text encoder (Hailo)
- `florence2_transformer_decoder.hef` - Decoder transformer (Hailo)
- `tokenizer.json` - HuggingFace tokenizer config
- `caption_embedding.npy` - Task embedding for captioning
- `vqa_embedding.npy` - Task embedding for VQA (optional, required for /v1/vqa)
- `word_embedding.npy` - Token embedding lookup for decoder

**Loading Strategy:**
1. Load all models at service startup
2. Keep resident in memory (persistent)
3. No lazy loading (avoid first-request latency spike)
4. Graceful teardown on service stop

### 3. systemd Service Management

**Service Type:** `Type=simple`

**Lifecycle:**
1. **Pre-Start:** Verify Hailo device availability
2. **Start:** Load models, initialize API server
3. **Ready:** Send sd_notify READY signal
4. **Running:** Handle requests, log to journald
5. **Stop:** Graceful shutdown, unload models
6. **Post-Stop:** Cleanup temporary resources

**Dependencies:**
```
After=network.target
Wants=network.target
```

**Resource Limits:**
- `MemoryMax=3G` - Hard memory cap
- `CPUQuota=70%` - Reserve headroom for OS and other services
- `TasksMax=50` - Limit subprocess count

**Restart Policy:**
- `Restart=on-failure`
- `RestartSec=10s`
- `StartLimitBurst=3`

---

## Resource Budget

### Memory Allocation

| Component | Memory | Notes |
|-----------|--------|-------|
| Vision Encoder (ONNX) | 500 MB | CPU RAM |
| Text Encoder (Hailo) | 500 MB | Hailo VRAM |
| Decoder (Hailo) | 1.5-2 GB | Hailo VRAM + shared mem |
| FastAPI Server | 200 MB | Python process overhead |
| Image Buffers | 100-200 MB | Input/output buffers |
| **Total** | **~3.5 GB** | **2-3 GB on Hailo** |

### CPU Usage
- **Idle:** <5%
- **Inference:** 30-50% (vision encoder on CPU)
- **Peaks:** Up to 100% during image decode/resize

### Hailo Device Utilization
- **Idle:** 0%
- **Inference:** 60-80% (text encoder + decoder)
- **Concurrent Services:** Compatible with hailo-ollama (different models)

### Thermal Impact
- **Moderate-High:** Decoder autoregressive generation produces sustained load
- **Recommendation:** Ensure adequate cooling (heatsink + airflow)
- **Throttling Risk:** Moderate (sustained 500ms inference bursts)

---

## Concurrent Service Compatibility

### Memory Budget Scenarios

**Scenario 1: florence + ollama (Recommended)**
- Florence-2: 3.5 GB total, 2-3 GB Hailo
- Ollama (Qwen2 1.8B): 2-3 GB total, 2 GB Hailo
- **Total:** ~6 GB system RAM, ~4-5 GB Hailo
- **Status:** ✅ Safe (within Pi 5 limits)

**Scenario 2: florence + clip**
- Florence-2: 3.5 GB total, 2-3 GB Hailo
- CLIP: 1.5 GB total, 1 GB Hailo
- **Total:** ~5 GB system RAM, ~3-4 GB Hailo
- **Status:** ✅ Comfortable

**Scenario 3: florence + vision (Qwen VLM)**
- Florence-2: 3.5 GB total, 2-3 GB Hailo
- Qwen VLM: 3-4 GB total, 2-4 GB Hailo
- **Total:** ~7 GB system RAM, ~5-7 GB Hailo
- **Status:** ⚠️ Tight (may swap, thermal throttling risk)

**Recommendation:** Run florence with either ollama OR vision, not both concurrently.

---

## API Design Decisions

### Why Two Endpoints?

Florence-2 supports multiple prompt tokens. The service exposes two focused tasks:

- **Captioning:** `/v1/caption` with the `<CAPTION>` task token
- **VQA:** `/v1/vqa` with the `<VQA>` task token

**Decision:** Keep the API small while covering the two primary use cases.

**Future:** Additional tasks (OCR, detection, grounded captioning) can be added if resources allow.

### Why No Streaming?

**Decision:** Return complete caption in single response.

**Rationale:**
- Florence-2 generates short captions (~20-100 tokens)
- Latency is dominated by encoder (200-300ms), not decoder
- Streaming adds complexity without meaningful latency reduction
- Pragmatic approach: simpler is better

**Alternative Considered:** SSE streaming (Server-Sent Events)
- **Rejected:** Not worth the implementation complexity

### Parameter Exposure

**Exposed:**
- `max_length` - User control over caption verbosity
- `min_length` - Prevent overly terse captions
- `temperature` - Sampling randomness (rarely needed)

**Not Exposed:**
- `top_k`, `top_p` - Rarely useful for captioning
- `num_beams` - Beam search not supported by current implementation

**Rationale:** Keep API simple, expose only commonly used parameters.

---

## Error Handling & Recovery

### Hailo Device Failures

**Scenario:** `/dev/hailo0` becomes unavailable (driver crash, hardware issue)

**Strategy:**
1. Health check endpoint returns 503 immediately
2. Caption requests fail with 503 + descriptive error
3. Service log error to journald
4. systemd restart policy kicks in (after 10s)
5. Restart attempts up to 3 times (StartLimitBurst=3)

**User Impact:** Temporary unavailability, automatic recovery in most cases

### Out-of-Memory (OOM)

**Scenario:** System runs out of RAM (concurrent services, memory leak)

**Strategy:**
1. `MemoryMax=3G` hard cap prevents runaway consumption
2. If limit hit, systemd kills service (SIGKILL)
3. Restart policy attempts recovery
4. Log OOM event to journald for diagnosis

**Prevention:**
- Careful memory budgeting
- Monitor with `systemctl status hailo-florence`
- Disable unnecessary concurrent services

### Model Inference Failures

**Scenario:** Inference returns error or invalid output

**Strategy:**
1. Catch exceptions in inference pipeline
2. Return 500 error with generic message (don't leak internal details)
3. Log full error trace to journald for debugging
4. Continue serving subsequent requests (don't crash service)

**Monitoring:** Track `requests_failed` metric via `/metrics` endpoint

---

## Logging & Monitoring

### Log Levels

- **INFO:** Startup, model loading, successful requests
- **WARNING:** Slow inference (>1.5s), memory pressure
- **ERROR:** Inference failures, device errors
- **DEBUG:** Detailed request/response data (disabled by default)

### Structured Logging

**Format:** JSON for machine readability

```json
{
  "timestamp": "2026-01-31T12:34:56Z",
  "level": "INFO",
  "message": "Caption generated successfully",
  "inference_time_ms": 782,
  "image_size_bytes": 524288,
  "caption_length": 23
}
```

### Journald Integration

All logs sent to systemd journal:
```bash
sudo journalctl -u hailo-florence -f
```

**Retention:** Follow system journal retention policy (typically 7-30 days)

### Metrics Endpoint

`GET /metrics` provides:
- Request counts (total, succeeded, failed)
- Latency percentiles (p50, p95, p99)
- Memory usage
- Uptime

**Usage:** Scrape for monitoring dashboards (Prometheus, Grafana)

---

## Security Considerations

### Current Deployment (localhost-only)

**Assumptions:**
- Service binds to `0.0.0.0:11438` but firewall blocks external access
- Trusted local users only
- No authentication required

**Risks:**
- Local privilege escalation if service has vulnerabilities
- Resource exhaustion via excessive requests

### Future Network Exposure

**If deploying on network:**

1. **Authentication:** Add API key validation
   ```python
   @app.middleware("http")
   async def verify_api_key(request, call_next):
       api_key = request.headers.get("X-API-Key")
       if api_key != os.getenv("API_KEY"):
           return JSONResponse({"error": "unauthorized"}, status_code=401)
       return await call_next(request)
   ```

2. **Rate Limiting:** Prevent DoS
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)
   
   @app.post("/v1/caption")
   @limiter.limit("10/minute")
   async def caption(...):
       ...
   ```

3. **Input Validation:** Strict image size/format checks
4. **HTTPS:** Encrypt data in transit (reverse proxy with TLS)
5. **Firewall:** Restrict access by IP/subnet

---

## Testing Strategy

### Unit Tests

**Scope:** Individual components in isolation

**Coverage:**
- Image preprocessing (decode, resize, normalize)
- Request validation (format, size, parameters)
- Response formatting
- Error handling

### Integration Tests

**Scope:** End-to-end API workflows

**Test Cases:**
1. **Happy Path:** Valid image → caption
2. **Invalid Image:** Malformed base64 → 400 error
3. **Large Image:** >10 MB image → 413 error
4. **Invalid Parameters:** max_length < 0 → 422 error
5. **Service Unavailable:** Model not loaded → 503 error
6. **Health Check:** Verify model status
7. **Metrics:** Request count increments

**Implementation:** pytest with fixtures

```python
@pytest.fixture
def api_client():
    return TestClient(app)

def test_caption_generation(api_client):
    with open("test_image.jpg", "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    response = api_client.post(
        "/v1/caption",
        json={"image": f"data:image/jpeg;base64,{image_b64}"}
    )
    
    assert response.status_code == 200
    assert "caption" in response.json()
    assert len(response.json()["caption"]) > 0
```

### Manual Verification

**verify.sh script:**
1. Check systemd service status
2. Verify Hailo device availability
3. Test health endpoint
4. Submit test image, validate response
5. Check metrics endpoint

---

## Deployment Workflow

### Installation Steps (install.sh)

1. **Pre-flight Checks**
   - Verify Hailo driver installed: `hailortcli fw-control identify`
   - Check Python version (3.10+)
   - Verify available memory (>4 GB free)

2. **User & Directory Setup**
   - Create `hailo-florence` system user
   - Create `/opt/hailo-florence/` (service directory)
   - Create `/var/lib/hailo-florence/` (data/model storage)
   - Create `/etc/hailo/hailo-florence.yaml` (configuration)
   - Render `/etc/xdg/hailo-florence/hailo-florence.json`
   - Set ownership and permissions

3. **Python Environment**
   - Install system dependencies: `libonnxruntime`, `opencv-python`
   - Install Python packages: `fastapi`, `uvicorn`, `pillow`, `transformers`
   - Copy Florence-2 implementation from hailo-rpi5-examples

4. **Model Files**
   - Download Florence-2 HEF files (encoder, decoder)
   - Download ONNX vision encoder
   - Download tokenizer config
   - Place in `/var/lib/hailo-florence/models/`

5. **Configuration**
   - Render config.yaml with `render_config.py`
   - Copy to `/etc/hailo/hailo-florence.yaml`

6. **systemd Service**
   - Copy `hailo-florence.service` to `/etc/systemd/system/`
   - Reload systemd daemon
   - Enable service (start on boot)
   - Start service

7. **Verification**
   - Run `verify.sh` to test API
   - Check logs for errors

### Uninstallation

1. Stop and disable service
2. Remove systemd unit file
3. Delete service directories
4. Remove user account
5. Reload systemd daemon

---

## Future Enhancements

### Performance Optimization
- **Batch Processing:** Accept multiple images in single request
- **Model Quantization:** Reduce VRAM usage (if Hailo supports FP16/INT8 Florence-2)
- **Cache Embeddings:** For repeated images (video frames)

### Feature Additions
- **Multi-Task Support:** OCR, object detection, grounded captioning
- **Streaming Responses:** SSE for token-by-token output
- **Scene Change Detection:** Avoid redundant captions for similar frames

### Operational Improvements
- **Prometheus Metrics:** Native Prometheus exporter
- **Grafana Dashboard:** Pre-built monitoring dashboard
- **Auto-Restart on Model Corruption:** Detect and recover from model file issues

---

## References

- **Florence-2 Paper:** https://arxiv.org/abs/2311.06242
- **Implementation Base:** [hailo-rpi5-examples/community_projects/dynamic_captioning](../../hailo-rpi5-examples/community_projects/dynamic_captioning/)
- **Hailo GenAI Reference:** C++ API in hailort/hailort/libhailort/include/hailo/genai/vlm/
- **System Setup:** [reference_documentation/system_setup.md](../../reference_documentation/system_setup.md)

---

**Last Updated:** January 31, 2026  
**Version:** 1.0.0  
**Status:** Design Complete, Ready for Implementation
