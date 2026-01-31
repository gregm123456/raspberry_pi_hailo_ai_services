# Hailo Face Recognition Service Architecture

Technical design and implementation details for the hailo-face system service.

## Overview

The hailo-face service provides a REST API for face detection, recognition, and identity management using Hailo-10H NPU acceleration. It wraps Hailo's face recognition pipeline with a Flask server and SQLite database for persistent identity storage.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Client Applications                     │
│         (cURL, Python, JavaScript, etc.)                │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP/REST (JSON)
                  │
┌─────────────────▼───────────────────────────────────────┐
│               Flask REST API Server                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Endpoints: /v1/detect, /v1/embed, /v1/recognize│   │
│  │             /v1/database/*                        │   │
│  └───────┬──────────────────────────────────┬───────┘   │
│          │                                   │           │
│  ┌───────▼───────────────┐         ┌────────▼────────┐  │
│  │ FaceRecognitionModel  │         │  FaceDatabase   │  │
│  │                       │         │                 │  │
│  │ - Detection (SCRFD)   │         │  SQLite DB      │  │
│  │ - Recognition (ArcFace│         │  - Identities   │  │
│  │ - Thread-safe         │         │  - Embeddings   │  │
│  └───────┬───────────────┘         └─────────────────┘  │
│          │                                               │
└──────────┼───────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────┐
│               Hailo-10H NPU (PCIe)                       │
│  ┌──────────────────┐      ┌──────────────────┐         │
│  │ Detection Model  │      │ Recognition Model │         │
│  │   SCRFD-10G      │      │ ArcFace MobileFaceNet │    │
│  │   (Face Bbox)    │      │   (512D Embedding)│         │
│  └──────────────────┘      └──────────────────┘         │
└──────────────────────────────────────────────────────────┘
```

## Components

### 1. Flask REST API Server

**Purpose:** HTTP interface for face recognition operations

**Implementation:**
- Framework: Flask (lightweight, synchronous)
- Threading: `threaded=True` for concurrent request handling
- Port: 5002 (default, configurable)
- Endpoints: Health check, detection, embedding, recognition, database management

**Why Flask?**
- Simple and pragmatic for small services
- Sufficient concurrency for Raspberry Pi workloads
- Easy debugging and log integration
- No need for async complexity (model inference is the bottleneck)

### 2. FaceRecognitionModel

**Purpose:** Wrapper for Hailo-accelerated face detection and recognition models

**Models:**
- **Detection:** SCRFD-10G (default) or RetinaFace  
  - Input: RGB image (any size)
  - Output: Bounding boxes, confidence scores, optional landmarks
  
- **Recognition:** ArcFace MobileFaceNet  
  - Input: Aligned face crop (112x112 typical)
  - Output: 512-dimensional L2-normalized embedding

**Model Loading Strategy:**
- **Persistent Loading:** Models loaded at service startup and kept resident in memory
- **Rationale:** Startup latency (~30-60s) makes on-demand loading impractical
- **Graceful Unload:** Not implemented (service restart required)

**Thread Safety:**
- Uses `threading.RLock()` for model access
- Prevents concurrent inference (Hailo device constraint)
- Queue handled by Flask's thread pool

**Mock Mode:**
- Fallback to mock inference if hailo-apps import fails
- Returns random embeddings/detections for development
- Enables testing without Hailo hardware

### 3. FaceDatabase

**Purpose:** Persistent storage for known face identities and embeddings

**Schema:**
```sql
identities:
  - id (PRIMARY KEY)
  - name (UNIQUE)
  - created_at
  - updated_at

embeddings:
  - id (PRIMARY KEY)
  - identity_id (FOREIGN KEY -> identities.id)
  - embedding (BLOB, 512 floats)
  - created_at
```

**Design Decisions:**
- **Multiple Embeddings Per Identity:** Supports face variations (angles, lighting)
- **SQLite:** Simple, file-based, no daemon required
- **Embedding Storage:** Binary blob (512 × 4 bytes = 2KB per embedding)
- **Matching:** Linear scan with cosine similarity (sufficient for small databases)

**Thread Safety:**
- `threading.RLock()` for database operations
- SQLite `SERIALIZED` mode (default)

**Backup:**
- Optional automatic backup on startup (configurable)
- Backup path: `/var/lib/hailo-face/backups/`

### 4. systemd Service Integration

**Unit Type:** `Type=simple`

**Why simple?**
- Flask's `app.run()` stays in foreground
- No forking or notification protocol needed
- Standard output goes to journald

**Dependencies:**
- `After=network-online.target` (wait for network)
- `Wants=network-online.target` (optional dependency)

**Resource Limits:**
- `MemoryMax=3G` (tuned for concurrent services)
- `CPUQuota=80%` (prevent thermal throttling)
- `TimeoutStartSec=120` (allow model loading time)

**User/Group:**
- Dedicated `hailo-face` user (non-login)
- Member of `video` group (for `/dev/hailo0` access)
- StateDirectory: `/var/lib/hailo-face`

## Data Flow

### Face Recognition Request

```
1. Client sends POST /v1/recognize with base64 image
2. Flask decodes image -> PIL Image
3. FaceRecognitionModel.detect_faces(image)
   -> Hailo SCRFD model inference
   -> Returns list of bounding boxes
4. For each detected face:
   a. FaceRecognitionModel.extract_embedding(image, bbox)
      -> Crop face region
      -> Hailo ArcFace model inference
      -> Returns 512D embedding
   b. FaceDatabase.find_match(embedding, threshold)
      -> Query all stored embeddings
      -> Compute cosine similarities
      -> Return best match above threshold
5. Aggregate results and return JSON response
```

### Add Identity Request

```
1. Client sends POST /v1/database/add with name and image
2. Detect face (auto-detect if no bbox provided)
3. Extract embedding from face region
4. FaceDatabase.add_identity(name, embedding)
   -> INSERT INTO identities (create or get ID)
   -> INSERT INTO embeddings (store blob)
5. Return success response
```

## Configuration

### YAML Structure

```yaml
server:
  host: 0.0.0.0
  port: 5002
  debug: false

face_recognition:
  detection_model: scrfd_10g
  recognition_model: arcface_mobilefacenet
  embedding_dimension: 512
  device: 0
  detection_threshold: 0.6
  recognition_threshold: 0.5
  max_faces: 10
  database_path: /var/lib/hailo-face/database

database:
  enabled: true
  db_file: /var/lib/hailo-face/faces.db
  backup_enabled: true
  backup_path: /var/lib/hailo-face/backups

performance:
  worker_threads: 2
  max_queue_size: 10
  request_timeout: 30
  warmup_enabled: false

resource_limits:
  memory_max: "3G"
  cpu_quota: "80%"

logging:
  level: INFO
  format: json
```

### Configuration Rendering

**Tool:** `render_config.py`

**Purpose:** Template variable substitution during installation

**Example:**
```bash
./render_config.py /etc/hailo/hailo-face.yaml server.port=5002
```

## Resource Management

### Memory Budget

**Target:** ~2-3GB total

**Breakdown:**
- Detection model: ~500MB
- Recognition model: ~200MB
- Flask/Python runtime: ~100MB
- Image buffers: ~200MB
- Database/embeddings: ~100MB (1000 identities)
- Overhead: ~500MB

**Concurrent Services:**
Must coordinate with other Hailo services (hailo-clip, hailo-vision, etc.) to stay within Raspberry Pi 5 memory limits (~6GB available).

### CPU Usage

**Target:** <80% average

**Strategies:**
- Flask threading limits concurrent CPU work
- Hailo NPU offloads inference (CPU mostly idle during forward pass)
- Minimal image preprocessing (resize, crop only)

### Startup Time

**Expected:** 30-60 seconds

**Factors:**
- Model loading from disk
- Hailo device initialization
- HEF compilation/caching
- Database initialization

**Optimization:**
- Models loaded once and kept resident
- No warmup iterations by default (configurable)

### Inference Latency

**Detection:** 30-50ms per image  
**Embedding:** 20-40ms per face  
**Recognition:** 50-150ms per image (including database search)

**Bottlenecks:**
1. Hailo device queue (single in-flight request)
2. Database linear search (O(n) with n identities)
3. Image decoding (base64 -> PIL)

## Scalability Considerations

### Database Size

**Current Implementation:** Linear scan of all embeddings

**Performance:**
- 10 identities: <5ms search
- 100 identities: ~20ms search
- 1000 identities: ~150ms search

**Future Optimizations (if needed):**
- FAISS/Annoy for approximate nearest neighbor
- Embedding pre-clustering
- Redis/in-memory cache for frequent searches

### Concurrent Requests

**Current:** Flask thread pool (2 workers by default)

**Limitations:**
- Hailo device processes requests serially
- Requests queue in Flask (max 10 by default)
- Higher concurrency requires batch inference support

### Multi-Device Support

**Not Currently Supported**

**Future:** Multiple Hailo devices could enable parallel inference with device pooling.

## Security Considerations

### Current State

- **No Authentication:** Internal service, assumed trusted network
- **No Input Validation:** Basic checks, could be strengthened
- **No Rate Limiting:** DoS risk if exposed externally

### Production Hardening

For external exposure, add:
1. API key authentication
2. Input size limits (max image size, request rate)
3. Reverse proxy (nginx) with rate limiting
4. HTTPS/TLS termination
5. Content-type validation

### Database Security

- SQLite file permissions: 755 (owner: hailo-face)
- No remote access (file-based)
- SQL injection: Protected by parameterized queries

## Testing Strategy

### Unit Tests

**Not yet implemented** (pragmatic choice for personal project)

**Future:** pytest fixtures for:
- FaceDatabase operations
- Mock model inference
- Embedding comparison

### Integration Tests

**Verification Script:** `verify.sh`

**Tests:**
1. systemd service status
2. Health endpoint reachability
3. Detection endpoint functionality
4. Database list endpoint

**Manual Testing:**
- Add identities via API
- Recognize faces in test images
- Verify database persistence across restarts

## Monitoring and Logging

### Logging

**Destination:** journald (via stdout/stderr)

**Format:** Line-based text (configurable JSON)

**Levels:**
- INFO: Startup, requests, model operations
- WARNING: Configuration issues, degraded performance
- ERROR: Inference failures, database errors

**Access:**
```bash
sudo journalctl -u hailo-face -f
```

### Health Monitoring

**Endpoint:** `GET /health`

**Checks:**
- Service running
- Models loaded
- Database accessible

**External Monitoring:**
- Prometheus exporter (future)
- Simple HTTP polling

## Failure Modes

### Model Loading Failure

**Symptom:** Service exits during startup  
**Recovery:** Check Hailo driver, model files, journald logs  
**Mitigation:** Mock mode fallback (development only)

### Database Corruption

**Symptom:** SQLite errors, write failures  
**Recovery:** Restore from backup, reinitialize database  
**Mitigation:** Automatic backups on startup

### Hailo Device Hang

**Symptom:** Inference timeout, requests queued indefinitely  
**Recovery:** Service restart (systemd `Restart=always`)  
**Mitigation:** Device timeout (5000ms default)

### Memory Exhaustion

**Symptom:** OOM killer, service crash  
**Recovery:** systemd restart, adjust MemoryMax  
**Mitigation:** Reduce concurrent services, lower queue size

## Future Enhancements

### Planned

1. **Full hailo-apps Integration:** Replace mock models with real pipeline
2. **Landmarks Support:** Return 5-point facial landmarks for alignment
3. **Video Stream Support:** WebRTC/RTSP input for live recognition
4. **Multiple Embeddings:** Store multiple samples per identity

### Considered

1. **Face Clustering:** Unsupervised grouping of unknown faces
2. **Age/Gender/Emotion:** Additional attribute detection
3. **Anti-Spoofing:** Liveness detection for photos-of-photos
4. **GPU Offload:** Use Pi's VideoCore for preprocessing

## Performance Tuning

### Optimize for Low Latency

```yaml
performance:
  worker_threads: 1  # Single-threaded avoids queue overhead
  warmup_enabled: true  # Pre-compile inference paths
```

### Optimize for Throughput

```yaml
performance:
  worker_threads: 4  # Higher parallelism
  max_queue_size: 20  # Larger queue
```

### Optimize for Memory

```yaml
resource_limits:
  memory_max: "2G"  # Tighter limit
face_recognition:
  max_faces: 5  # Process fewer faces per image
```

## References

- Hailo Model Zoo: [ArcFace MobileFaceNet](https://github.com/hailo-ai/hailo_model_zoo)
- SCRFD Paper: [Sample and Computation Redistribution for Efficient Face Detection](https://arxiv.org/abs/2105.04714)
- ArcFace Paper: [Additive Angular Margin Loss for Deep Face Recognition](https://arxiv.org/abs/1801.07698)
- systemd Documentation: [systemd.service(5)](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

## Version History

- **v1.0.0** (2026-01-31): Initial implementation with mock models
- Future: Full hailo-apps integration, production hardening
