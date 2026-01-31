# Hailo Whisper Service Architecture

Design decisions and implementation details for speech-to-text on Hailo-10H.

## Overview

`hailo-whisper` provides Whisper-based speech-to-text transcription accelerated by the Hailo-10H NPU. The service follows the established patterns of other Hailo services (hailo-ollama, hailo-vision) with adaptations specific to audio processing workloads.

## Design Goals

1. **OpenAI API Compatibility** - Support standard Whisper API format for easy integration
2. **Persistent Model Loading** - Keep models resident to minimize latency
3. **Resource Efficiency** - Optimize NPU usage while managing limited Pi 5 resources
4. **Format Flexibility** - Support multiple output formats (JSON, SRT, VTT, text)
5. **Production-Ready** - systemd integration, health checks, logging

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Client Application                    │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (multipart/form-data)
                       ▼
┌─────────────────────────────────────────────────────────┐
│              hailo-whisper Service (Port 11436)         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  aiohttp Web Server (async)                       │  │
│  │  - POST /v1/audio/transcriptions                  │  │
│  │  - GET /health, /health/ready                     │  │
│  │  - GET /v1/models                                 │  │
│  └──────────────┬────────────────────────────────────┘  │
│                 │                                         │
│  ┌──────────────▼────────────────────────────────────┐  │
│  │  WhisperService (model lifecycle)                 │  │
│  │  - Model loading/unloading                        │  │
│  │  - Audio preprocessing                            │  │
│  │  - Inference orchestration                        │  │
│  └──────────────┬────────────────────────────────────┘  │
│                 │                                         │
└─────────────────┼─────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              Hailo-10H NPU (/dev/hailo0)                │
│  - Whisper Encoder (mel-spectrogram → embeddings)      │
│  - Whisper Decoder (embeddings → tokens)               │
└─────────────────────────────────────────────────────────┘
```

## Component Design

### 1. HTTP API Layer (APIHandler)

**Responsibilities:**
- Parse multipart/form-data requests (audio files)
- Validate inputs (file size, format, required fields)
- Format responses (JSON, text, SRT, VTT)
- Error handling and status codes

**Key Design Decisions:**
- **Multipart Form Data**: Required for file uploads (OpenAI Whisper API standard)
- **Max File Size**: 25MB limit (configurable via aiohttp `client_max_size`)
- **Temporary Storage**: Audio files saved to `/var/lib/hailo-whisper/cache` during processing
- **Response Formats**: Multiple formats to support subtitles, plain text, structured JSON

### 2. Service Layer (WhisperService)

**Responsibilities:**
- Model lifecycle management (load, keep alive, unload)
- Audio file decoding and preprocessing
- NPU inference orchestration
- Cleanup of temporary files

**Key Design Decisions:**
- **Persistent Loading**: Model loaded at startup, kept resident (avoids 5-10s reload latency)
- **Cache Directory**: `/var/lib/hailo-whisper/cache` for temporary audio files
- **Async Processing**: Non-blocking inference for handling concurrent requests
- **VAD Filtering**: Voice Activity Detection to remove silence/noise

### 3. Model Lifecycle

**Loading Strategy:**
```
Service Start → Load Model → Ready for Inference
                    ↓
              Keep Resident (keep_alive=-1)
                    ↓
              Service Shutdown → Unload Model
```

**Configuration Options:**
- `keep_alive: -1` - Persistent (recommended, default)
- `keep_alive: 0` - Unload after each request (high latency)
- `keep_alive: N` - Unload after N seconds idle

**Rationale**: Whisper models are 100-500MB and take 5-10 seconds to load. Persistent loading is essential for reasonable latency.

## Resource Management

### Memory Budget

| Component          | Memory (Small) | Memory (Medium) |
|--------------------|----------------|-----------------|
| Whisper Model (NPU)| ~400 MB        | ~1.2 GB         |
| Audio Preprocessing| ~100 MB        | ~200 MB         |
| Runtime Overhead   | ~100 MB        | ~150 MB         |
| **Total**          | ~600 MB        | ~1.5 GB         |

**systemd Limits:**
- `MemoryMax=3G` - Hard limit (safe for whisper-small on Pi 5)
- Adjust for larger models (whisper-medium requires ~4G)

### CPU Usage

- **Audio Decoding**: CPU-bound (ffmpeg/librosa)
- **Feature Extraction**: CPU-bound (mel-spectrogram computation)
- **Inference**: NPU-accelerated (encoder + decoder)

**systemd Limits:**
- `CPUQuota=80%` - Leave headroom for other services

### NPU Utilization

- **Concurrent Services**: Hailo-10H supports multiple services (hailo-whisper can run alongside hailo-vision, hailo-ollama)
- **Memory Sharing**: NPU has 8GB DRAM shared across all services
- **Budget Planning**: Allocate ~400MB for whisper-small, ~1.2GB for whisper-medium

## Audio Processing Pipeline

```
Audio File (mp3/wav/ogg)
    ↓
Decode to PCM (ffmpeg/librosa)
    ↓
Resample to 16kHz Mono
    ↓
Extract Mel-Spectrogram Features
    ↓
Encoder Inference (NPU)
    ↓
Decoder Inference (NPU, autoregressive)
    ↓
Token-to-Text Conversion
    ↓
VAD Filtering (optional)
    ↓
Segment Timestamps
    ↓
Format Output (JSON/SRT/VTT/Text)
```

## Model Variants

### whisper-tiny
- Parameters: 39M
- Memory: ~200 MB
- Latency: Low
- Accuracy: Basic

### whisper-base
- Parameters: 74M
- Memory: ~300 MB
- Latency: Low
- Accuracy: Good

### whisper-small (default)
- Parameters: 244M
- Memory: ~400 MB
- Latency: Medium
- Accuracy: Very Good

### whisper-medium
- Parameters: 769M
- Memory: ~1.2 GB
- Latency: High
- Accuracy: Excellent

**Recommendation**: Start with `whisper-small` for best balance of accuracy and resource usage.

## Security Considerations

### systemd Hardening

```ini
NoNewPrivileges=true         # Prevent privilege escalation
PrivateTmp=true              # Isolated /tmp
ProtectSystem=strict         # Read-only /usr, /boot, /efi
ProtectHome=true             # No access to /home
ReadWritePaths=/var/lib/hailo-whisper  # State directory only
DeviceAllow=/dev/hailo0 rw   # NPU device only
```

### Input Validation

- **File Size Limit**: 25MB max (prevent DoS)
- **Audio Duration Limit**: 300 seconds max (configurable)
- **MIME Type Validation**: Check file headers
- **Path Traversal Prevention**: Temporary files in controlled directory

### Temporary File Management

- Files saved to `/var/lib/hailo-whisper/cache`
- Unique filenames (NamedTemporaryFile)
- Automatic cleanup after transcription
- Ownership: `hailo-whisper:hailo-whisper`

## Monitoring and Observability

### Health Checks

- **Liveness**: `GET /health` - Service running?
- **Readiness**: `GET /health/ready` - Model loaded?

### Metrics

- `uptime_seconds` - Service uptime
- `transcriptions_processed` - Total transcription count
- `model_loaded` - Model loaded status

### Logging

- **systemd journald** - All logs via `journalctl -u hailo-whisper`
- **Log Levels**: INFO (startup, config), ERROR (failures)
- **Structured Logging**: Timestamp, component, level, message

## Scalability Considerations

### Single Instance Limits

- **Concurrent Requests**: Limited by NPU and CPU capacity
- **Audio Duration**: 300s default (5 minutes)
- **File Size**: 25MB default

### Performance Optimization

- **Persistent Model Loading**: Eliminates 5-10s startup per request
- **Async Processing**: Non-blocking I/O for HTTP and file operations
- **VAD Filtering**: Reduces processing time by skipping silence

### Scaling Strategies

- **Vertical**: Larger models for better accuracy (trade memory/latency)
- **Horizontal**: Multiple Pi 5 units with load balancer (if needed)
- **Queue-Based**: Add Redis/RabbitMQ for asynchronous job processing

## Integration Patterns

### Direct API Calls

```python
import requests
response = requests.post(url, files={"file": audio}, data={"model": "whisper-small"})
```

### OpenAI SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:11436/v1")
transcript = client.audio.transcriptions.create(model="whisper-small", file=audio)
```

### Reverse Proxy (nginx)

```nginx
upstream hailo-whisper {
    server localhost:11436;
}

server {
    listen 443 ssl;
    server_name whisper.example.com;
    
    location / {
        proxy_pass http://hailo-whisper;
        proxy_set_header Host $host;
        client_max_body_size 26M;
    }
}
```

## Future Enhancements

- **Model Repository**: Automatic model download and caching
- **Batch Processing**: Process multiple files in parallel
- **Translation**: Whisper translation mode (speech-to-text in English)
- **Speaker Diarization**: Identify different speakers
- **Real-Time Streaming**: WebSocket-based streaming transcription
- **Model Quantization**: INT4 quantization for even lower memory usage

## References

- [OpenAI Whisper](https://github.com/openai/whisper)
- [Whisper API Docs](https://platform.openai.com/docs/api-reference/audio)
- [Hailo Developer Zone](https://hailo.ai/developer-zone/)
- [HailoRT Documentation](https://hailo.ai/developer-zone/documentation/)
