# Hailo SCRFD Service Architecture

System design and technical decisions for the SCRFD face detection service.

---

## Overview

The hailo-scrfd service provides **face detection with 5-point facial landmarks** using the SCRFD (Sample and Computation Redistribution for Face Detection) model accelerated on the Hailo-10H NPU. It exposes a REST API for real-time face detection and alignment suitable for face recognition pipelines.

**Key Design Principles:**
- **Persistent model loading** — Load SCRFD model at startup, keep resident in memory
- **Thread-safe inference** — Handle concurrent requests with locking
- **Lightweight dependencies** — Flask for REST, OpenCV for image processing
- **Standard formats** — COCO-style bounding boxes, named landmarks
- **Integration-ready** — Designed to feed hailo-face (ArcFace) service

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     HTTP Client                          │
│              (curl, Python, browser)                     │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API (port 5001)
                        │
┌───────────────────────▼─────────────────────────────────┐
│              Flask Application Layer                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  /health    │  │  /v1/detect  │  │  /v1/align   │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  SCRFDModel Class                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Model Loading (startup)                         │  │
│  │  - Load HEF from hailo-apps                      │  │
│  │  - Initialize postprocessing pipeline            │  │
│  │  - Set confidence/NMS thresholds                 │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Face Detection (per request)                    │  │
│  │  1. Preprocess: resize to 640×640, normalize    │  │
│  │  2. Inference: run HailoRT inference             │  │
│  │  3. Postprocess: decode boxes, landmarks, NMS   │  │
│  │  4. Scale results back to original image size   │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Face Alignment (optional)                       │  │
│  │  - Similarity transform using 5 landmarks        │  │
│  │  - Output 112×112 aligned face for recognition  │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              HailoRT (libhailort)                        │
│  - PCIe communication with Hailo-10H                    │
│  - Model execution on NPU                               │
│  - Output tensor collection                             │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              Hailo-10H NPU (/dev/hailo0)                │
│  - SCRFD model execution (2.5G or 10G variant)          │
│  - Multi-scale feature extraction                       │
│  - Anchor-based detection                               │
└─────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. Flask Application

**Technology:** Flask (simple, proven, low overhead)

**Endpoints:**
- **`GET /health`** — Health check, model status
- **`POST /v1/detect`** — Face detection with landmarks
- **`POST /v1/align`** — Face detection + alignment

**Threading Model:**
- `threaded=True` for concurrent request handling
- Each request spawns a thread
- Thread-safe model inference with `threading.RLock()`

### 2. SCRFDModel Class

**Responsibilities:**
- Load SCRFD HEF model from hailo-apps
- Manage model lifecycle (load at startup, persist)
- Execute inference with thread safety
- Postprocess outputs (bbox, landmarks, NMS)

**Key Methods:**
- `load()` — Load model at startup (blocking, called once)
- `detect_faces(image: np.ndarray)` — Run inference (thread-safe)
- `_run_inference(image)` — Low-level HailoRT inference
- Internal locking ensures safe concurrent access

**Model Loading Strategy:**
```python
def load(self) -> bool:
    with self.lock:
        if self.is_loaded:
            return True
        
        # Import from hailo-apps
        from hailo_apps.postprocess.cpp import scrfd
        
        # Load HEF and initialize
        self.model = scrfd.SCRFD(
            model_path="/path/to/scrfd.hef",
            conf_threshold=self.conf_threshold,
            nms_threshold=self.nms_threshold,
        )
        
        self.is_loaded = True
        return True
```

### 3. Configuration Management

**YAML Configuration** (`/etc/hailo/hailo-scrfd.yaml`)
- Human-readable, operator-friendly
- Supports tuning thresholds, buffer sizes, resource limits

**JSON Configuration** (`/etc/xdg/hailo-scrfd/hailo-scrfd.json`)
- Rendered from YAML by `render_config.py`
- Used by hailo-apps components if needed

**Configuration Loading:**
- Config loaded at startup by `SCRFDServiceConfig`
- Changes require service restart
- Validate on load, fall back to defaults on error

### 4. Image Processing Pipeline

**Input Processing:**
1. Base64 decode (strip data URI prefix if present)
2. PIL Image load and convert to RGB
3. Convert to numpy array (H, W, 3)

**Preprocessing for Inference:**
1. Resize to 640×640 (SCRFD input size)
2. Normalize pixel values (model-specific)
3. Channel order adjustment if needed (RGB vs. BGR)

**Postprocessing:**
1. Parse output tensors (bbox, classification, landmarks)
2. Apply confidence threshold filtering
3. NMS to remove duplicate detections
4. Scale coordinates back to original image size

**Face Alignment:**
1. Use 5 landmarks to compute similarity transform
2. Align to standard face template (eyes horizontal, nose centered)
3. Warp and crop to 112×112 (ArcFace standard size)

---

## SCRFD Model Details

### Model Variants

| Model | GFLOPs | Parameters | Input Size | AP (WIDER FACE) |
|-------|--------|-----------|-----------|-----------------|
| **scrfd_2.5g_bnkps** | 2.5 | ~2.5M | 640×640 | 82% |
| **scrfd_10g_bnkps** | 10 | ~10M | 640×640 | 92% |

**Recommendation:** Use `scrfd_2.5g_bnkps` for most cases (good balance of speed and accuracy).

### Model Architecture

**Backbone:** ResNet-like feature extractor  
**Neck:** Feature Pyramid Network (FPN) — 3 scales  
**Heads:**
- **Classification head:** Face/no-face
- **Bounding box head:** 4 coordinates (x, y, w, h)
- **Landmark head:** 10 values (5 landmarks × 2 coords)

**Anchor-based Detection:**
- Predefined anchor boxes at multiple scales
- Offset regression for precise localization
- Anchor stride: 8, 16, 32 pixels

### Output Tensor Format

```
Classification:  [batch, num_anchors, 1]      # Face confidence
Bounding Boxes:  [batch, num_anchors, 4]      # x, y, w, h offsets
Landmarks:       [batch, num_anchors, 10]     # 5 landmarks × (x, y)
```

**Postprocessing Steps:**
1. Apply sigmoid to classification scores
2. Decode box offsets to absolute coordinates
3. Decode landmark offsets to absolute coordinates
4. Filter by confidence threshold
5. NMS with IoU threshold
6. Scale to original image dimensions

---

## Concurrency & Thread Safety

### Request Handling

**Flask Threading:**
- Each HTTP request handled in separate thread
- No shared state between requests (except model)
- Flask's built-in threading sufficient for 2-10 concurrent requests

**Model Locking:**
```python
with self.lock:
    detections = self.model.detect(image)
```

**Why Locking:**
- HailoRT may not be fully thread-safe
- Prevents race conditions in postprocessing
- Simple RLock allows re-entrant calls

**Performance Impact:**
- Lock held only during inference (~15-30ms)
- Minimal contention for typical workloads (<5 concurrent requests)
- For high concurrency, consider multi-process with load balancer

### Resource Limits

**systemd Configuration:**
```ini
MemoryMax=2G       # Prevent memory exhaustion
CPUQuota=80%       # Leave headroom for other services
```

**Tuning Worker Threads:**
```yaml
performance:
  worker_threads: 2    # Flask thread pool size
  max_queue_size: 10   # Request queue depth
```

---

## Deployment Strategy

### systemd Service

**Unit Type:** `Type=simple`
- Single-process service
- Flask runs in foreground
- Systemd manages lifecycle

**Startup Sequence:**
1. systemd starts service
2. Python interpreter loads
3. Config parsed
4. SCRFD model loaded (60-90 seconds)
5. Flask starts listening
6. systemd marks service as active

**Extended Startup Timeout:**
```ini
TimeoutStartSec=120   # Model loading takes time
```

### Persistent Model Loading

**Design Decision:** Load model at startup and keep resident

**Rationale:**
- Model loading is expensive (60-90 seconds)
- On-demand loading unacceptable for low-latency applications
- Memory cost (1-2 GB) is acceptable on Pi 5

**Alternative Considered:** On-demand loading with timeout
- **Rejected:** First request incurs 60-90s latency
- **Rejected:** Complex timeout/unload logic

---

## Resource Constraints

### Memory Budget

**Service Footprint:**
- Python interpreter: ~50 MB
- SCRFD model (2.5G): 1-1.5 GB
- SCRFD model (10G): 1.5-2 GB
- Flask + OpenCV: ~100 MB
- Request buffers: ~50-100 MB per concurrent request

**Total:** 1.2-2.5 GB depending on model and concurrency

### Raspberry Pi 5 Total Budget

**Available Memory:** ~6 GB (8 GB model minus OS)

**Multi-service Scenario:**
- hailo-ollama: 4-6 GB
- hailo-scrfd: 1.5-2 GB
- hailo-vision: 1-2 GB

**Total:** 6.5-10 GB — **exceeds budget**

**Mitigation:**
- Run SCRFD + vision services (4-5 GB total) ✓
- OR run LLM alone
- Consider swapping services on-demand (systemctl stop/start)

### Thermal Considerations

**SCRFD Thermal Impact:** Low-Moderate

**Sustained Load:**
- Continuous inference at 30-60 fps
- NPU power draw: 2-5W
- Additional CPU for preprocessing: 1-2W

**Cooling Recommendations:**
- Passive cooling sufficient for <30 fps
- Active cooling (fan) for sustained 60 fps
- Monitor with: `vcgencmd measure_temp`

---

## Integration Patterns

### Face Recognition Pipeline

**Typical Workflow:**
```
Input Image
  ↓
hailo-scrfd: Detect faces, get landmarks
  ↓
hailo-scrfd: Align faces to 112×112
  ↓
hailo-face (ArcFace): Extract 512D embeddings
  ↓
Database: Compare embeddings, identify person
```

**Service Communication:**
- Sequential REST calls (detect → align → embed)
- Each service runs independently
- Client orchestrates pipeline

### Concurrent Service Deployment

**Compatible Services:**
- hailo-clip (port 5000) + hailo-scrfd (port 5001) ✓
- hailo-scrfd + hailo-vision (shared vision workloads) ✓
- hailo-scrfd + hailo-face (full face recognition stack) ✓

**Incompatible (memory):**
- hailo-scrfd + hailo-ollama (LLM too large) ✗

---

## Design Trade-offs

### 1. Persistent vs. On-Demand Model Loading

**Choice:** Persistent loading at startup

| Approach | Pros | Cons |
|----------|------|------|
| **Persistent** | Low latency, simple logic | Higher memory, slower startup |
| **On-demand** | Lower memory, faster startup | 60-90s first request, complex timeout logic |

**Decision:** Persistent — latency matters more than memory for real-time use cases.

### 2. Threading vs. Multiprocessing

**Choice:** Threading with RLock

| Approach | Pros | Cons |
|----------|------|------|
| **Threading** | Simple, low overhead | GIL contention, shared state requires locking |
| **Multiprocessing** | True parallelism, no GIL | High memory (N× models), complex IPC |

**Decision:** Threading — sufficient for 2-10 concurrent requests, much simpler.

### 3. Flask vs. FastAPI

**Choice:** Flask

| Framework | Pros | Cons |
|-----------|------|------|
| **Flask** | Battle-tested, simple, low overhead | Synchronous, manual thread management |
| **FastAPI** | Async, auto-generated docs | Higher complexity, more dependencies |

**Decision:** Flask — proven, simple, adequate performance for this workload.

---

## Future Enhancements

### Potential Improvements

1. **Batch Inference**
   - Process multiple images in one inference call
   - Improve throughput for video streams

2. **Model Caching**
   - Cache aligned faces for repeated requests
   - LRU eviction policy

3. **Streaming Video Support**
   - WebSocket or SSE for video frames
   - Frame skipping for real-time processing

4. **Face Tracking**
   - Track face IDs across frames
   - Reduce false positives with temporal consistency

5. **Quality Metrics**
   - Blur detection (discard low-quality faces)
   - Pose estimation (frontal vs. profile)
   - Occlusion detection (partial faces)

---

## References

- **SCRFD Paper:** [arXiv:2105.04714](https://arxiv.org/abs/2105.04714)
- **Hailo Model Zoo:** SCRFD model specifications
- **hailo-apps:** `hailo_apps/postprocess/cpp/scrfd.cpp`

---

## See Also

- [README.md](README.md) — Installation and usage
- [API_SPEC.md](API_SPEC.md) — REST API reference
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues
