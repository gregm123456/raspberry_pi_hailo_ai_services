# Plan: Full Async/Await Modernization for hailo-depth Service

**Date:** February 6, 2026  
**Author:** Greg  
**Goal:** Migrate hailo-depth from callback-based HailoInfer to async/await using HailoDeviceClient, enabling device manager serialization and transparent model switching. Mirror the successful hailo-ocr pattern.

**Rationale:** Current hailo-depth uses synchronous HailoInfer with threading.Event, blocking the event loop. This prevents concurrent requests and doesn't integrate with device manager. Async/await modernization matches Group A services, improves responsiveness, and allows device manager to handle model lifecycle.

**Scope:** Refactor hailo_depth_server.py (~400 LOC), add DepthHandler to device_manager (~100 LOC), update tests. Keep API unchanged; internal async flow only.

**Risk:** Medium - Requires careful tensor encoding/decoding. Rollback to callback adapter if issues.

**Timeline:** 1-2 weeks (implementation + testing).

---

## Prerequisites

- Hailo-10H driver installed: `hailortcli fw-control identify`
- Device manager running: `systemctl status hailo-device-manager`
- hailo-depth service installed but stopped: `sudo systemctl stop hailo-depth`
- Python 3.10+, aiohttp, numpy, pillow in venv
- Model HEF downloaded to `/var/lib/hailo-depth/resources/models/scdepthv3.hef`
- Access to hailo-ocr code as reference

---

## Implementation Steps

### Step 1: Add DepthHandler to Device Manager

**Why:** Device manager needs a handler for `model_type="depth"` to serialize inference requests.

**Files Modified:**
- `device_manager/hailo_device_manager.py`

**Changes:**

1. **Add DepthHandler class** (after OcrHandler, ~lines 407-500):

```python
@dataclass
class DepthHandler(ModelHandler):
    """Handler for depth estimation models (e.g., scdepthv3)."""

    def __init__(self, config: dict):
        self.config = config

    async def load_model(self, model_path: str, model_params: Optional[Dict[str, Any]] = None) -> Any:
        """Load depth model into HailoRT."""
        # Similar to OcrHandler.load_model but single-stage
        try:
            from hailo_platform import HEF, FormatType, HailoRTException
            hef = HEF(model_path)
            network_groups = hef.get_network_groups()
            if len(network_groups) != 1:
                raise ValueError(f"Expected 1 network group, got {len(network_groups)}")
            network_group = network_groups[0]
            network_group_params = network_group.create_configure_params(FormatType.FLOAT32)
            configured_network_group = network_group.configure(network_group_params)
            return configured_network_group
        except Exception as e:
            logger.error(f"Failed to load depth model {model_path}: {e}")
            raise

    async def run_inference(self, configured_network_group: Any, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run depth inference."""
        # Decode input tensor
        input_tensor = decode_tensor(input_data['input'])
        
        # Bind input/output
        input_vstream_info = configured_network_group.get_input_vstream_infos()[0]
        output_vstream_info = configured_network_group.get_output_vstream_infos()[0]
        
        with configured_network_group.activate() as network_group_runner:
            input_vstream = network_group_runner.create_input_vstream(input_vstream_info)
            output_vstream = network_group_runner.create_output_vstream(output_vstream_info)
            
            # Run inference
            input_vstream.send(input_tensor)
            output_tensor = output_vstream.recv()
            
            # Encode output tensor
            return {'output': encode_tensor(output_tensor)}
```

2. **Update handler registry** (~line 541):

```python
handlers = {
    'vlm': VlmHandler,
    'vlm_chat': VlmChatHandler,
    'whisper': WhisperHandler,
    'ocr': OcrHandler,
    'depth': DepthHandler,  # Add this
}
```

3. **Update supported model_types** (~line 547):

```python
supported_model_types = ['vlm', 'vlm_chat', 'whisper', 'ocr', 'depth']
```

**Testing:** Restart device manager: `sudo systemctl restart hailo-device-manager`. Check logs for no errors.

---

### Step 2: Define Depth Model I/O Contract

**Why:** Ensure device manager handler matches hailo-depth's expectations.

**Contract:**
- **Input:** Single tensor `{dtype: "float32", shape: [1, 3, 256, 320], data_b64: "..."}` (preprocessed image)
- **Output:** Single tensor `{dtype: "float32", shape: [1, 1, 256, 320], data_b64: "..."}` (depth map)
- **Model:** scdepthv3.hef (monocular depth, input 256x320x3, output 256x320x1)

**Files Modified:**
- `device_manager/API_SPEC.md` (add depth section under "Model Types")

**Changes:** Add after OCR section:

```markdown
**depth** - Monocular depth estimation using scdepthv3
- Input: Preprocessed image tensor (float32, [1,3,H,W])
- Output: Depth map tensor (float32, [1,1,H,W])
```

---

### Step 3: Refactor hailo-depth to Use HailoDeviceClient

**Why:** Replace synchronous HailoInfer with async device manager calls.

**Files Modified:**
- `system_services/hailo-depth/hailo_depth_server.py`

**Changes:**

1. **Import device client** (after existing imports, ~line 20):

```python
from device_client import HailoDeviceClient
```

2. **Add tensor helpers** (after decode_tensor, ~line 84):

```python
def encode_tensor(array: np.ndarray) -> Dict[str, Any]:
    """Encode numpy array as base64 for device manager."""
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
    }

def decode_tensor(payload: Dict[str, Any]) -> np.ndarray:
    """Decode base64 tensor from device manager."""
    dtype = payload.get("dtype")
    shape = payload.get("shape")
    data_b64 = payload.get("data_b64")

    if not dtype or shape is None or not data_b64:
        raise ValueError("Invalid tensor payload")

    raw = base64.b64decode(data_b64)
    array = np.frombuffer(raw, dtype=np.dtype(dtype))
    return array.reshape(shape).copy()
```

3. **Update DepthEstimator class:**

   - **Remove HailoInfer imports/usage** (~lines 55-100): Remove `HailoInfer` from imports, remove `self.infer` and related.

   - **Add client to __init__** (~line 126):

```python
self.client: Optional[HailoDeviceClient] = None
```

   - **Refactor initialize()** (~lines 141-205): Replace model loading with async client connect and load_model.

```python
async def initialize(self):
    logger.info(f"Initializing depth model: {self.config.model_name}")
    model_path = os.path.join(self.config.model_dir, f"{self.config.model_name}.hef")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    
    # Connect to device manager
    self.client = HailoDeviceClient()
    await self.client.connect()
    
    # Load model via device manager
    await self.client.load_model(model_path, model_type="depth")
    
    self.is_loaded = True
    logger.info("Depth model loaded successfully")
```

   - **Refactor estimate_depth()** (~lines 207-292): Replace `_run_inference_sync` with async client.infer.

```python
async def estimate_depth(self, image_data: bytes, normalize: bool = None, colormap: str = None, output_format: str = None) -> Dict[str, Any]:
    start_time = time.time()
    
    # Preprocess (unchanged)
    img = Image.open(io.BytesIO(image_data)).convert('RGB')
    input_tensor = self._preprocess_image(img)
    
    # Encode for device manager
    input_payload = encode_tensor(input_tensor)
    
    # Run inference via device manager
    result = await self.client.infer(self.model_path, input_data={'input': input_payload})
    
    # Decode output
    output_tensor = decode_tensor(result['output'])
    
    # Postprocess (unchanged)
    depth_map = self._extract_depth_output({'output': output_tensor})
    # ... rest of postprocessing ...
    
    inference_time = time.time() - start_time
    return {
        'model': self.config.model_name,
        'model_type': 'monocular',
        'input_shape': list(input_tensor.shape),
        'depth_shape': list(depth_map.shape),
        'inference_time_ms': inference_time * 1000,
        # ... rest ...
    }
```

   - **Remove _run_inference_sync()** (~lines 358-393): Delete entire method.

   - **Add disconnect in shutdown** (new method or in main):

```python
async def shutdown(self):
    if self.client:
        await self.client.disconnect()
```

4. **Update main()** (~lines 684-717): Make async, call initialize() and shutdown().

```python
async def main():
    estimator = DepthEstimator(config)
    try:
        await estimator.initialize()
        app = await create_app(estimator)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.server_host, config.server_port)
        await site.start()
        logger.info(f"Server started on {config.server_host}:{config.server_port}")
        # Wait forever
        await asyncio.Future()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await estimator.shutdown()
```

5. **Update create_app()** (~lines 668-680): Remove sync lock, as async handles concurrency.

**Testing:** Run `python hailo_depth_server.py` manually, check logs for async flow.

---

### Step 4: Update Service Configuration & Permissions

**Files Modified:**
- `system_services/hailo-depth/hailo-depth.service`

**Changes:**
- Ensure PYTHONPATH includes device_client.py location (if not in venv).
- Confirm service user `hailo-depth` is in `hailo-device-mgr` group for socket access.

**Commands:**
```bash
sudo usermod -aG hailo-device-mgr hailo-depth
sudo systemctl daemon-reload
```

---

### Step 5: Add Tests

**Files Modified/Created:**
- `system_services/hailo-depth/tests/test_hailo_depth_async.py` (new)

**Content:**
- Unit tests for tensor encode/decode.
- Mock device manager for async inference flow.
- Integration test: Start service, send POST /v1/depth/estimate, verify response.

**Run Tests:**
```bash
cd system_services/hailo-depth
python -m pytest tests/test_hailo_depth_async.py -v
```

---

## Testing & Validation

1. **Unit Tests:** Pass tensor encoding, mock inference.
2. **Integration:** Start hailo-depth, device manager. Send requests, check logs for async flow, no blocking.
3. **Concurrency:** Run multiple curl requests simultaneously, verify serialization.
4. **Performance:** Benchmark inference time vs old version.
5. **API Compatibility:** Ensure /health, /v1/info, /v1/depth/estimate work unchanged.

**Commands:**
```bash
# Start services
sudo systemctl start hailo-device-manager
sudo systemctl start hailo-depth

# Test API
curl http://localhost:11439/health
curl -X POST http://localhost:11439/v1/depth/estimate -F "image=@test.jpg"

# Concurrent test
for i in {1..5}; do curl -X POST http://localhost:11439/v1/depth/estimate -F "image=@test.jpg" & done
```

---

## Rollback Plan

If issues: Revert to callback adapter (add HailoInferAdapter class, change import in hailo_depth_server.py).

NOTE: Do not roll back without approval.

**Commands:**
```bash
git checkout <commit-before-changes>
sudo systemctl restart hailo-depth
```

---

## Success Criteria

- hailo-depth starts without errors.
- Inference requests succeed with async logs.
- Concurrent requests serialized via device manager.
- No performance regression.
- API unchanged for clients.

**Hand-off:** Implement steps 1-5 in order. Test thoroughly. Report any blockers.</content>
<parameter name="filePath">/home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-depth/PLAN_hailo-dept_full_async.md
