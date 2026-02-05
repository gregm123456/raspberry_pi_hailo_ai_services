# Device Manager Feature Branch Integration Notes

The `device-manager` branch introduces a **Hailo Device Manager** service designed to coordinate exclusive access to the Hailo-10H NPU, enabling multiple AI services to run concurrently by serializing inference requests. This addresses the core limitation where only one service can use the NPU at a time, causing conflicts when multiple services attempt direct device access.

## Key Differences from `main`

### 1. New Device Manager Service (`device_manager/` directory)
- **`hailo_device_manager.py`**: The main daemon that holds the exclusive VDevice connection, manages a request queue, and processes inference calls via a Unix socket API (`/run/hailo/device.sock`).
- **`device_client.py`**: A client library that services import to communicate with the manager instead of creating VDevice instances directly.
- **`hailo-device-manager.service`**: systemd unit file for running the manager as a persistent service.
- **`install.sh`**: Installation script that sets up the service, virtual environment, and socket.
- Test files: `test_device_manager_concurrency.py`, `test_concurrent_services.py`, etc., for validating concurrency and integration.
- Documentation: `README.md`, `API_SPEC.md`, `ARCHITECTURE.md`, `TEST_FINDINGS.md`.

### 2. Modified Existing Services
- Services like `hailo-clip`, `hailo-ollama`, and `hailo-vision` (and potentially others) have been updated to use `HailoDeviceClient` for inference instead of direct `VDevice` access.
- **Before** (in `main`): Services create their own VDevice, leading to conflicts.
  ```python
  from hailo_platform import VDevice
  vdevice = VDevice(params)
  # Direct inference...
  ```
- **After** (in `device-manager` branch): Services use the client for queued, serialized requests.
  ```python
  from device_client import HailoDeviceClient
  async with HailoDeviceClient() as client:
      await client.load_model(hef_path, model_type="vlm")
      result = await client.infer(hef_path, input_data, model_type="vlm")
  ```
- This allows multiple services to coexist without crashes, with models cached centrally for efficiency.

### 3. Other Changes
- Updated `.github/copilot-instructions.md` and `README.md` to reflect the device manager.
- Added/modified files in `system_services/` for various services (e.g., new test files, config updates), but the core difference is the shift to client-based access.
- The branch was developed when only `hailo-clip`, `hailo-ollama`, and `hailo-vision` were fully working; other services exist but may be in draft form or untested without the manager integration.

## Benefits of Integration
- **Concurrency**: Multiple services can run simultaneously (e.g., vision + CLIP + Ollama) without device conflicts.
- **Efficiency**: Models are loaded once and cached, reducing memory usage.
- **Reliability**: Proper error handling and status monitoring via the centralized manager.
- **Scalability**: Easy to add new services using the client library.

## Integration Steps
To integrate into `main`, merge the `device-manager` branch. The services in `main` would need updates to adopt the client pattern, similar to what's done in the branch.