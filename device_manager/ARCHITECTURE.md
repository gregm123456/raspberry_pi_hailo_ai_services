# Hailo Device Manager Architecture

## Purpose

Provide a single, always-on process that owns the Hailo-10H VDevice and serializes all model loads and inference calls for multiple services. This avoids device contention and makes each AI service a thin client.

## Core Responsibilities

- Maintain the exclusive Hailo device and VDevice
- Expose a Unix socket API for requests and responses
- Serialize all device operations through a single-worker queue
- Cache loaded models in memory and reuse across requests
- Provide basic status and health data

## Design Constraints

- **Single Hailo access:** Only one process can safely own a Hailo VDevice at a time.
- **RAM budget:** Raspberry Pi 5 has limited available RAM; model caching must be selective.
- **Thermal limits:** Sustained inference can throttle CPU, so background load is kept small.
- **Service isolation:** Clients must not require direct access to /dev/hailo0.

## High-Level Architecture

```
┌──────────────────────────────────────────────┐
│ systemd: hailo-device-manager.service        │
│  - User: hailo-device-mgr                    │
│  - Exec: /opt/hailo-device-manager/...       │
└──────────────────────────────────────────────┘
                    │
                    v
┌──────────────────────────────────────────────┐
│ Hailo Device Manager (Python asyncio)        │
│  - Unix socket server: /run/hailo/device.sock│
│  - Request queue (single worker)             │
│  - Model registry + handler registry         │
│  - Hailo VDevice + Device ownership          │
└──────────────────────────────────────────────┘
                    │
                    v
┌──────────────────────────────────────────────┐
│ Hailo-10H device (/dev/hailo0)               │
└──────────────────────────────────────────────┘

Clients (hailo-vision, hailo-clip, hailo-ollama, etc.)
connect via Unix socket and submit JSON requests.
```

## Component Breakdown

### Unix Socket API

- Location: `/run/hailo/device.sock`
- Protocol: length-prefixed JSON over Unix socket
- Supports: `ping`, `status`, `load_model`, `infer`, `unload_model`

### Request Serialization

- Incoming requests are placed into an asyncio queue
- A single worker uses a one-thread executor to call Hailo APIs
- This guarantees only one device operation runs at any time

### Model Registry

- Cache key: `model_type:model_path`
- Cache entries track load time and last use
- Load-on-demand for `infer` if not present

### Model Handlers

- `vlm`: Hailo GenAI VLM
- `vlm_chat`: VLM chat using `generate_all`
- `clip`: image and text encoders using `create_infer_model`

Add new model types by extending the handler registry in the manager.

## Deployment Model

- systemd unit: [hailo-device-manager.service](hailo-device-manager.service)
- Restart policy: `Restart=always` with `RestartSec=5`
- Runtime directory: `/run/hailo`
- Logging: journald via stdout/stderr

## Python Runtime Strategy

- Virtual environment: `/opt/hailo-device-manager/venv`
- Uses system site packages for HailoRT bindings
- Manager script copied to `/opt/hailo-device-manager/hailo_device_manager.py`

## Resource Limits

From the systemd unit:

- `CPUQuota=20%`
- `MemoryMax=512M`

These keep the manager lightweight and prevent memory contention with the AI services.

## Known Limitations

- Single device operations only; all inference is serialized
- Model caching can consume RAM if many large HEF files are loaded
- No request prioritization or timeout enforcement yet
- Single socket path; no multi-tenant namespaces

## Future Improvements

- Priority queueing for latency-sensitive services
- Request timeout and cancellation
- Model pre-warming at startup
- Metrics for queue depth, inference time, and model residency
- Multi-device support if multiple Hailo boards are installed
