# Hailo Piper TTS Architecture

Design decisions and system architecture for the Hailo Piper TTS service.

## Overview

The Hailo Piper TTS service wraps the Piper TTS engine as a persistent systemd service, exposing a REST API for text-to-speech synthesis on Raspberry Pi 5. **Unlike other Hailo services, this runs purely on CPU without requiring the Hailo-10H NPU.**

**⚠️ Important Version Note:** This service requires **Piper TTS 1.3.0** specifically. Version 1.4.0 has breaking changes and compatibility issues:
- Requires system-wide `espeak-ng` installation (not bundled)
- Has phoneme handling bugs causing `wave.Error: # channels not specified`
- Not backwards compatible with 1.3.0's self-contained design

See [Hailo Community: Piper TTS 1.4.0 Issues](https://community.hailo.ai/t/piper-tts-1-4-0-tts-synthesis-playback-failed-channels-not-specified/18701) for details.

## Design Philosophy

**Pragmatic Standards:** Adopts the OpenAI `/v1/audio/speech` API pattern for compatibility with existing clients and tools.

**Simplicity:** Single-model persistent loading; no complex model management or hot-swapping.

**Reliability:** systemd-managed service with automatic restarts and health monitoring.

## System Components

### 1. Flask REST API Server

**Purpose:** HTTP interface for speech synthesis requests

**Location:** `/opt/hailo-piper/hailo_piper_service.py`

**Key Features:**
- Threaded Flask server for concurrent requests
- JSON request/response handling
- Binary audio file responses
- Error handling and logging

**Endpoints:**
- `GET /health` - Service health check
- `POST /v1/audio/speech` - OpenAI-compatible synthesis
- `POST /v1/synthesize` - Alternative synthesis endpoint
- `GET /v1/voices` - List available voices

### 2. Piper TTS Engine

**Purpose:** Neural text-to-speech synthesis

**Backend:** Piper TTS (ONNX Runtime + phonemization)

**Model Format:** ONNX models with JSON configuration

**Integration:**
- Persistent model loading at service startup
- Thread-safe synthesis with locking
- In-memory WAV generation
- Configurable synthesis parameters

**Resource Usage:**
- Memory: 200-500MB (model dependent)
- CPU: 50-80% during synthesis
- Synthesis speed: 2-5x real-time

**Installation:**
- **piper-tts version:** Must be pinned to 1.3.0 (see Overview for version compatibility notes)
- **Dependencies:** 1.3.0 includes bundled `espeakbridge.so` and `espeak-ng-data/` (~13.8 MB wheel)
- **No NPU required:** Pure CPU inference using ONNX Runtime

### 3. Configuration Management

**YAML Config:** `/etc/hailo/hailo-piper.yaml`

Operator-facing configuration for:
- Server settings (host, port, debug)
- Piper model path and synthesis parameters
- Performance tuning
- Resource limits

**JSON Config:** `/etc/xdg/hailo-piper/hailo-piper.json`

Auto-generated from YAML; used internally if needed.

**Render Script:** `render_config.py`

Validates and converts YAML to JSON during installation.

### 4. systemd Service

**Unit File:** `/etc/systemd/system/hailo-piper.service`

**Type:** `simple` (foreground process)

**Key Settings:**
- Runs as dedicated user `hailo-piper:hailo-piper`
- Working directory: `/var/lib/hailo-piper`
- State directory for models and cache
- Environment variables for XDG paths
- Automatic restart on failure
- Resource limits: 2G memory, 80% CPU quota

**Lifecycle:**
1. systemd starts service
2. Python script loads Piper model
3. Flask server binds to port 5003
4. Service enters ready state
5. Handles synthesis requests
6. On shutdown, graceful cleanup

## Data Flow

### Synthesis Request Flow

```
Client Request
    ↓
Flask Endpoint (/v1/audio/speech)
    ↓
Request Validation (text length, format)
    ↓
PiperTTS.synthesize()
    ↓
[Model Lock Acquired]
    ↓
Piper Voice Model (ONNX)
    ↓
WAV Generation (in-memory)
    ↓
[Model Lock Released]
    ↓
send_file() → Client
```

**Threading:** Thread-safe with `threading.RLock()` protecting model access

**Concurrency:** Multiple requests can queue; synthesis is serialized

## Resource Model

### Memory Budget

**Base Service:** ~50MB (Python + Flask)

**Piper Model:**
- Small models: ~100MB
- Medium models: ~200-300MB
- Large models: ~500MB+

**Total:** ~200-550MB depending on model size

**No Hailo Device Required:** Pure CPU inference

### CPU Usage

**Idle:** <5% CPU

**Synthesis:** 50-80% CPU per request

**Concurrent Requests:** Serialized due to model lock; queued synthesis

### Disk Usage

**Service Code:** <1MB

**Models:** 50-400MB per voice model

**Cache/State:** Minimal (<10MB)

## Security Considerations

### Service Isolation

- Dedicated system user (`hailo-piper`) with no login shell
- Runs with minimal privileges
- No Hailo device access needed (unlike other services)
- State directory restricted to service user

### Network Exposure

- Default: Listens on all interfaces (0.0.0.0:5003)
- Recommendation: Use firewall to restrict access
- No authentication built-in (add reverse proxy for production)

### Input Validation

- Maximum text length enforced (5000 chars)
- Format validation (WAV, PCM only)
- JSON schema validation
- SQL injection prevention (no database)
- No file system access from user input

## Performance Optimization

### Model Loading Strategy

**Persistent Loading:** Model loaded once at startup, kept in memory

**Rationale:** Model loading is slow (~2-5s); persistent loading eliminates per-request overhead

**Trade-off:** Higher memory usage vs. lower latency

### Synthesis Pipeline

**In-Memory Processing:** WAV generation in `io.BytesIO`, no disk I/O

**Thread Safety:** Single model instance with lock; simple and reliable

**Streaming:** Not implemented; full synthesis before response

### Caching Strategy

**Current:** No audio caching implemented

**Future:** Optional audio cache for frequently synthesized phrases

## Integration Points

### Voice Model Management

**Model Location:** `/var/lib/hailo-piper/models/`

**Model Format:**
- `.onnx` - ONNX model file
- `.onnx.json` - Model configuration

**Model Selection:** Configured in YAML; single model per service instance

**Model Switching:** Requires service restart

### Logging

**Destination:** systemd journal (journalctl)

**Format:** Python logging with timestamps

**Log Levels:**
- INFO: Startup, requests, synthesis
- WARNING: Model issues, configuration problems
- ERROR: Synthesis failures, exceptions

**Access:**
```bash
journalctl -u hailo-piper.service -f
```

## Deployment Considerations

### Single-Model Design

**Current:** One model per service instance

**Rationale:**
- Simplicity
- Predictable resource usage
- Fast startup

**Multi-Voice Support:** Deploy multiple service instances on different ports

### Concurrent Requests

**Strategy:** Thread-safe serialization via model lock

**Scaling:**
- Vertical: Increase worker threads (limited by serialization)
- Horizontal: Run multiple service instances with load balancer

### Resource Limits

**systemd Limits:**
- `MemoryMax=2G` - Prevent runaway memory usage
- `CPUQuota=80%` - Prevent CPU starvation
- `TimeoutStartSec=120` - Allow model loading time

**Tuning:** Adjust based on model size and Pi 5 workload

## Failure Modes

### Model Loading Failure

**Cause:** Missing model files, corrupted model

**Detection:** Service fails to start

**Recovery:** Check logs, re-download model, verify paths

### Synthesis Failure

**Cause:** Invalid text, model error, resource exhaustion

**Detection:** 500 error response

**Recovery:** Automatic (stateless per-request); service remains healthy

### Port Conflict

**Cause:** Another service using port 5003

**Detection:** Service fails to start

**Recovery:** Change port in config, restart service

### Resource Exhaustion

**Cause:** Too many concurrent requests, memory leak

**Detection:** OOM, high CPU, slow response

**Recovery:** systemd restarts service automatically

## Design Trade-offs

### Persistent Model Loading

**Pro:**
- Low per-request latency
- Simple lifecycle

**Con:**
- Higher memory footprint
- Single model per instance

**Decision:** Persistent loading for personal/art projects; latency matters more than memory

### Thread-Safe Serialization

**Pro:**
- Simple, reliable
- No race conditions

**Con:**
- Limited concurrency
- Queue delays under load

**Decision:** Simplicity over high-throughput; typical use case is low-volume

### OpenAI API Compatibility

**Pro:**
- Familiar API pattern
- Existing client libraries
- Drop-in replacement potential

**Con:**
- Some parameters not applicable (e.g., speaker)

**Decision:** Adopt standard over custom API; pragmatic choice

## Future Enhancements

### Streaming Synthesis

**Goal:** Stream audio chunks as they're synthesized

**Benefit:** Lower time-to-first-audio

**Complexity:** Moderate (chunked encoding)

### Audio Caching

**Goal:** Cache synthesized audio for repeated phrases

**Benefit:** Instant response for cached text

**Complexity:** Low (LRU cache with hash keys)

### Multi-Model Support

**Goal:** Switch voices without service restart

**Benefit:** Flexibility

**Complexity:** Moderate (model registry, lazy loading)

### Format Support

**Goal:** MP3, OGG, FLAC output

**Benefit:** Smaller file sizes, broader compatibility

**Complexity:** Moderate (add format conversion pipeline)

## References

- [Piper TTS GitHub](https://github.com/rhasspy/piper)
- [ONNX Runtime](https://onnxruntime.ai/)
- [systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [Flask Documentation](https://flask.palletsprojects.com/)
