# Hailo Device Manager - Exclusive Device Access & Request Serialization

## Problem & Solution

**The Problem:** Only one service can actively use the Hailo-10H NPU at a time. When multiple services try to create inference contexts (VDevice), the second fails with:
```
HAILO_OUT_OF_PHYSICAL_DEVICES(74): Failed to create vdevice. 
there are not enough free devices. requested: 1, found: 0
```

**The Solution:** A centralized **Device Manager** that:
- Holds the exclusive VDevice connection
- Serializes inference requests from multiple services
- Provides a Unix socket API for request/response communication
- Services become lightweight clients instead of direct device users

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Hailo Device Manager                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────┐       ┌──────────────────────┐   │
│  │  Exclusive VDevice   │       │  Request Queue       │   │
│  │  (Single instance)   │       │  (Serializes all     │   │
│  │                      │       │   inference calls)   │   │
│  └──────────────────────┘       └──────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┤
│  │  Unix Socket API @ /run/hailo/device.sock                │
│  └──────────────────────────────────────────────────────────┤
│                                                              │
└─────────────────────────────────────────────────────────────┘

        ▲              ▲              ▲
        │              │              │
        │              │              │
    ┌───────────┐  ┌──────────┐  ┌──────────┐
    │  Hailo    │  │  Hailo   │  │  Hailo   │
    │  Vision   │  │  Ollama  │  │  Face    │
    │ (Client)  │  │ (Client) │  │ (Client) │
    └───────────┘  └──────────┘  └──────────┘
```

## Files

- **`hailo_device_manager.py`** — Main daemon (manages device, processes requests via queue)
- **`device_client.py`** — Client library (services import this to communicate)
- **`hailo-device-manager.service`** — systemd unit file
- **`install.sh`** — Installation script
- **`test_device_manager_concurrency.py`** — Concurrency test for manager queue + optional inference
- **`test_concurrent_services.py`** — Integration test for hailo-vision + hailo-clip
- **`test_concurrent_services.sh`** — Bash integration test (health checks + log sampling)
- **`test_multi_network_load.py`** — Research script for multi-network feasibility
- **`TEST_FINDINGS.md`** — Historical test notes and analysis

## Prerequisites

- Hailo driver installed: `sudo apt install dkms hailo-h10-all`
- HailoRT Python bindings: `sudo apt install python3-h10-hailort`
- Verify: `hailortcli fw-control identify`

## Installation

```bash
# Install the device manager
cd /home/gregm/raspberry_pi_hailo_ai_services/device_manager
sudo ./install.sh
```

This will:
1. Create system user `hailo-device-mgr`
2. Set up Python virtual environment
3. Install systemd service
4. Create socket at `/run/hailo/device.sock`
5. Enable and start the service

It also writes `/etc/hailo/device-manager.env` for optional overrides
(`HAILO_DEVICE_SOCKET`, socket permissions, message size limits).

## Configuration

Edit `/etc/hailo/device-manager.env` to override defaults:

```bash
HAILO_DEVICE_SOCKET=/run/hailo/device.sock
HAILO_DEVICE_SOCKET_MODE=0660
HAILO_DEVICE_SOCKET_GROUP=hailo
HAILO_DEVICE_MAX_MESSAGE_BYTES=8388608
```

## Usage by Services

Services update their code to use the device manager client instead of direct device access:

### Before (Direct Device Access - FAILS WITH CONFLICTS)
```python
from hailo_platform import VDevice
from hailo_platform.genai import VLM

vdevice = VDevice(params)
vlm = VLM(vdevice, hef_path)
result = vlm.infer(data)
```

### After (Through Device Manager - WORKS IN PARALLEL)
```python
from device_manager.device_client import HailoDeviceClient

async with HailoDeviceClient() as client:
    # Load model (only loads once, then cached)
    await client.load_model(hef_path, model_type="vlm")
    
    # Run inference (queued at manager, serialized)
    result = await client.infer(hef_path, input_data, model_type="vlm")
```

## Device Manager API

The manager listens on Unix socket at `/run/hailo/device.sock` and accepts
length-prefixed JSON requests. Each request can include a `request_id` that
is echoed back in the response.

### ping
Check connection and get uptime:
```json
{"action": "ping", "request_id": "..."}
```

### status
Get device status and loaded models:
```json
{"action": "status", "request_id": "..."}
```

### load_model
Load a model into device memory:
```json
{
  "action": "load_model",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "model_params": {},
  "request_id": "..."
}
```

### infer
Run inference (auto-loads model if needed):
```json
{
  "action": "infer",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "input_data": {...},
  "request_id": "..."
}
```

### Tensor Payload Format

Some model types (e.g., `vlm_chat`, `clip`) send tensors in `input_data`:

```json
{
  "dtype": "uint8",
  "shape": [1, 224, 224, 3],
  "data_b64": "..."
}
```

`data_b64` is base64-encoded raw bytes for the array.

### unload_model
Remove model from device memory:
```json
{
  "action": "unload_model",
  "model_path": "/path/to/model.hef",
  "model_type": "vlm",
  "request_id": "..."
}
```

### Supported Model Types

Currently supported `model_type` values:
- `vlm` (Hailo GenAI VLM via `hailo_platform.genai.VLM`)
- `vlm_chat` (VLM chat via `VLM.generate_all`)
- `clip` (CLIP image/text encoders via `create_infer_model`)

Add new model types by extending the handler registry in
`hailo_device_manager.py`.

## Service Integration Steps

To integrate a service with the device manager:

1. **Stop the service:**
   ```bash
   sudo systemctl stop hailo-SERVICE-NAME
   ```

2. **Update service code** to use `HailoDeviceClient` instead of creating VDevice directly

3. **Copy device_client.py** to service directory or install in shared location

4. **Test the integration:**
   ```bash
   # Start device manager
   sudo systemctl start hailo-device-manager.service
   
   # Start service (now using device manager)
   sudo systemctl start hailo-SERVICE-NAME
   
   # Check logs
   sudo journalctl -u hailo-device-manager.service -f
   sudo journalctl -u hailo-SERVICE-NAME -f
   ```

## Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **Concurrent Services** | Only 1 can infer at a time | N services can coexist (queued) |
| **Device Conflicts** | Services crash if both try to infer | Gracefully serialized by manager |
| **Model Memory** | Each service loads its own copy | Manager caches models (memory efficient) |
| **Error Handling** | Service crashes if device unavailable | Manager returns proper error to client |
| **Monitoring** | No centralized device status | Manager exposes unified device status |
| **Scaling** | Must stop/start services to add more | Simply add new services using client |

## Testing

### Test the device manager independently:
```bash
# In one terminal, watch device manager logs
sudo journalctl -u hailo-device-manager.service -f

# In another, test client
cd /opt/hailo-device-manager
./venv/bin/python3 device_client.py
```

### Concurrency test:
```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/device_manager
python3 test_device_manager_concurrency.py
```

Optional inference test inputs:
```bash
export HAILO_TEST_MODEL_PATH=/path/to/model.hef
export HAILO_TEST_MODEL_TYPE=vlm_chat
export HAILO_TEST_INPUT_JSON=/path/to/input.json
python3 test_device_manager_concurrency.py
```

### Test multi-service scenario:
```bash
# Start both services (hailo-vision + hailo-clip)
sudo systemctl start hailo-vision.service
sudo systemctl start hailo-clip.service

# Python integration test
python3 test_concurrent_services.py

# Bash integration test (health checks + log sampling)
./test_concurrent_services.sh
```

## Architecture Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — Design, constraints, and internal structure
- [API_SPEC.md](API_SPEC.md) — Unix socket protocol and request schema
- [TEST_FINDINGS.md](TEST_FINDINGS.md) — Historical test results and initial analysis
- [test_multi_network_load.py](test_multi_network_load.py) — Research script for multi-network feasibility

## Performance Notes
### Device Manager Model Caching & Persistence

**Model Residency:**
The device manager holds models in memory and reuses them across requests—models stay loaded in the Hailo-10H device memory (VRAM) as long as the manager is running. Once a model is loaded, subsequent inference calls from any service do not reload it from disk.

**How It Works:**
1. **Single Exclusive VDevice:** The device manager process owns the only VDevice connection to `/dev/hailo0`. Services (hailo-vision, hailo-clip, hailo-whisper, etc.) cannot create their own VDevice—they would fail with `HAILO_OUT_OF_PHYSICAL_DEVICES`.
2. **Model Registry & Caching:** The manager maintains a registry of loaded models. When a service requests inference:
  - If the model is already loaded, it is reused immediately.
  - If not, it is loaded from disk into the VDevice, cached, and then used for inference.
3. **Request Serialization:** All inference requests are queued and processed by a single worker thread. This guarantees only one model runs inference at a time, prevents device contention, and allows requests to wait in queue while models stay resident.
4. **Model Lifecycle:**
  - **Load time:** Once, on first inference call
  - **Residency:** Manager keeps models loaded until `unload_model` is called or manager shuts down
  - **Memory:** Cached models consume Hailo-10H VRAM, not Pi CPU RAM

**Service Integration:**
When services use `HailoDeviceClient`, they send inference requests to the manager. The manager handles model loading, caching, and serialization. Services do not duplicate model memory and benefit from efficient VRAM usage.

**Current State:**
If services are not yet integrated with the device manager, each service manages its own device access and model loading, which can lead to conflicts and inefficient memory use. Once integrated, the device manager architecture enables concurrent, efficient operation.

### Hailo-10H VRAM vs Pi CPU RAM

The Hailo-10H NPU has 8 GB of dedicated VRAM, separate from the Raspberry Pi's CPU RAM (e.g., 4 GB). The device manager loads models into Hailo VRAM, not CPU RAM, so model caching does not compete with service memory. This allows multiple large models to remain resident on the NPU, enabling concurrent service operation without exhausting system RAM. Services send inference requests to the manager, which reuses cached models in VRAM for efficiency. Only the device manager holds the exclusive VDevice and manages model residency; services do not duplicate model memory.

- **Inference Latency**: +~10-20ms per request (IPC overhead)
- **Throughput**: Limited by single device, not by manager (queueing is fast)
- **Memory**: Reduced compared to multiple services each loading models
- **Startup**: Services start instantly; models load on first inference request
- **Concurrent Requests (Without Manager)**: Services like hailo-clip (config allows 2 worker threads, but not implemented in code) and hailo-vision queue requests under load, with latencies increasing 10-100x (e.g., 200ms → 20s for CLIP, 4s → 20s for Vision) but handle gracefully without crashes

## Troubleshooting

### Device manager won't start
```bash
sudo journalctl -u hailo-device-manager.service -n 50 --no-pager
```

### Service can't connect to device manager
- Verify socket exists: `ls -l /run/hailo/device.sock`
- Check socket permissions: `stat /run/hailo/device.sock`
- Verify device manager is running: `systemctl status hailo-device-manager.service`

### Inference hangs or times out
- Check service logs for queue depth and model load logs
- Verify previous inferences completed
- Restart device manager: `sudo systemctl restart hailo-device-manager.service`

## Future Enhancements

- Priority queue (video-inference prioritized over background analysis)
- Request timeout handling
- Model pre-warming (load models at startup, not on first inference)
- Metrics/telemetry (inference times, queue depth, device utilization)
- Multi-device support (if Hailo-10H devices are added)
