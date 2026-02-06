# Plan: Hailo-OCR Full Async/Await Modernization

**Date:** February 5, 2026  
**Objective:** Migrate hailo-ocr from direct HailoInfer (Group B) to device manager integration with pure async/await patterns (Group A architecture).  
**Rationale:** Architecturally cleaner, follows established patterns in hailo-vision, hailo-whisper, and hailo-clip. Eliminates callback bridging complexity. REST API remains unchanged—this is purely internal improvement.  
**Estimated Effort:** 7-10 hours  
**Risk Level:** Medium (new device manager handler, multi-model coordination)  

## Overview

Current hailo-ocr uses direct `HailoInfer` with callback-to-async bridging (Group B). This works but adds complexity and potential latency. Group A services (hailo-vision, hailo-whisper, hailo-clip) use `HailoDeviceClient` with pure async/await, enabling concurrent operation through centralized device manager.

**Key Changes:**
- Replace `HailoInfer` instances with `HailoDeviceClient`
- Remove callback bridging from `run_detection()` and `run_recognition()`
- Add unified `OcrHandler` to device manager for multi-model support (detection + recognition)
- Service becomes thin async client; device manager handles NPU inference and batching
- Preserve hailo-apps pre/post-processing utilities

**Architecture After Migration:**
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  hailo-ocr     │    │ Device Manager   │    │ Hailo-10H NPU  │
│  Service       │────│ (OcrHandler)     │────│                │
│  (Async Client)│    │ - Detection      │    │                │
└─────────────────┘    │ - Recognition    │    └─────────────────┘
                       │ - Batching       │
                       └──────────────────┘
```

## Steps

### 1. Implement Unified OCR Handler in Device Manager

**File:** [device_manager/hailo_device_manager.py](device_manager/hailo_device_manager.py)  
**Location:** Add after `WhisperHandler` (around line 220)  

Create `OcrRuntime` dataclass and `OcrHandler` class following CLIP's multi-model pattern:

```python
@dataclass
class OcrRuntime:
    detection_model: Any
    recognition_models: Dict[str, Any]  # lang -> InferModel
    batch_sizes: Dict[str, int]

class OcrHandler(ModelHandler):
    model_type = "ocr"

    def load(self, vdevice: hailo_platform.VDevice, model_path: str, model_params: Dict[str, Any]) -> Any:
        det_hef_path = model_params.get("detection_hef_path")
        rec_hefs = model_params.get("recognition_hefs", {})  # {lang: path}
        batch_sizes = model_params.get("batch_sizes", {})

        detection_model = vdevice.create_infer_model(det_hef_path)
        recognition_models = {}
        for lang, hef_path in rec_hefs.items():
            recognition_models[lang] = vdevice.create_infer_model(hef_path)

        return OcrRuntime(
            detection_model=detection_model,
            recognition_models=recognition_models,
            batch_sizes=batch_sizes
        )

    def infer(self, model: OcrRuntime, input_data: Any) -> Any:
        mode = input_data.get("mode")
        if mode == "detection":
            # Single detection inference
            image_tensor = decode_tensor(input_data["image"])
            with model.detection_model.configure() as configured_model:
                bindings = configured_model.create_bindings()
                bindings.input().set_buffer(image_tensor)
                configured_model.run([bindings])
                output = bindings.output().get_buffer()
                return encode_tensor(output)

        elif mode == "recognition":
            # Batched recognition inference
            lang = input_data.get("language", "en")
            crops = [decode_tensor(crop) for crop in input_data.get("crops", [])]
            batch_size = input_data.get("batch_size", model.batch_sizes.get(lang, 8))

            # Handle batching with padding
            results = []
            for i in range(0, len(crops), batch_size):
                batch = crops[i:i + batch_size]
                actual_batch_size = len(batch)

                # Pad to batch_size if needed
                if actual_batch_size < batch_size:
                    padding_shape = (batch_size - actual_batch_size,) + batch[0].shape
                    padding = np.zeros(padding_shape, dtype=batch[0].dtype)
                    batch.extend([padding] * (batch_size - actual_batch_size))

                # Run batch inference
                infer_model = model.recognition_models[lang]
                with infer_model.configure() as configured_model:
                    bindings_list = []
                    for j in range(batch_size):
                        bindings = configured_model.create_bindings()
                        bindings.input().set_buffer(batch[j])
                        bindings_list.append(bindings)

                    configured_model.run(bindings_list)

                    # Collect outputs, trim padding
                    batch_outputs = []
                    for j in range(actual_batch_size):
                        output = bindings_list[j].output().get_buffer()
                        batch_outputs.append(encode_tensor(output))

                    results.extend(batch_outputs)

            return results

        else:
            raise ValueError(f"Unknown OCR mode: {mode}")

    def unload(self, model: OcrRuntime) -> None:
        # Cleanup if needed
        pass
```

**Register Handler:** Add to handler registry in `HailoDeviceManager.__init__()`:
```python
self._handlers = {
    # ... existing handlers ...
    OcrHandler.model_type: OcrHandler(),
}
```

### 2. Copy Device Client to Service Directory

**File:** [system_services/hailo-ocr/device_client.py](system_services/hailo-ocr/device_client.py)  
**Action:** Copy entire [device_manager/device_client.py](device_manager/device_client.py) to service directory  

This allows local import without depending on device_manager package structure.

### 3. Refactor HailoOCRService Initialization

**File:** [system_services/hailo-ocr/hailo_ocr_server.py](system_services/hailo-ocr/hailo_ocr_server.py)  
**Changes:**  
- Remove `HailoInfer` import (lines ~30-45)  
- Add `from device_client import HailoDeviceClient`  
- Replace `self.det_infer` and `self.rec_infers` with client and model paths  
- Update `initialize()` to use device manager  

```python
class HailoOCRService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client: Optional[HailoDeviceClient] = None
        self.detection_model_path: Optional[str] = None
        self.recognition_model_paths: Dict[str, str] = {}
        self.batch_sizes: Dict[str, int] = {}
        # ... other fields ...

    async def initialize(self):
        # Resolve model paths
        self.detection_model_path = self._resolve_model_path(
            self.config['hailo_models']['detection_hef']
        )

        for lang, hef_name in self.config['hailo_models'].get('recognition_hefs', {}).items():
            self.recognition_model_paths[lang] = self._resolve_model_path(hef_name)
            self.batch_sizes[lang] = self.config['hailo_models'].get('batch_size_rec', 8)

        # Initialize device client
        self.client = HailoDeviceClient()
        await self.client.connect()

        # Load OCR models via device manager
        model_params = {
            "detection_hef_path": self.detection_model_path,
            "recognition_hefs": self.recognition_model_paths,
            "batch_sizes": self.batch_sizes,
        }

        await self.client.load_model(
            self.detection_model_path,  # Use detection path as primary key
            model_type="ocr",
            model_params=model_params
        )

        self.is_loaded = True
```

### 4. Convert Detection to Pure Async

**File:** [system_services/hailo-ocr/hailo_ocr_server.py](system_services/hailo-ocr/hailo_ocr_server.py)  
**Method:** `run_detection()` (lines ~155-172)  

Replace callback bridging with direct async call:

```python
async def run_detection(self, image_np: np.ndarray) -> Tuple[List[np.ndarray], List[List[int]]]:
    h, w, _ = self._get_detection_input_shape()  # Extract from config or hardcoded
    processed = resize_with_padding(image_np, target_height=h, target_width=w)

    response = await self.client.infer(
        self.detection_model_path,
        {
            "mode": "detection",
            "image": encode_tensor(processed),
        },
        model_type="ocr",
    )

    raw_result = decode_tensor(response["result"])
    crops, boxes = det_postprocess(raw_result, image_np, h, w)
    return crops, boxes
```

**Note:** Need to import `encode_tensor` and `decode_tensor` from device_client or hailo_device_manager.

### 5. Convert Recognition to Pure Async

**File:** [system_services/hailo-ocr/hailo_ocr_server.py](system_services/hailo-ocr/hailo_ocr_server.py)  
**Method:** `run_recognition()` (lines ~177-221)  

Replace callback bridging with single async call (device manager handles batching):

```python
async def run_recognition(self, crops: List[np.ndarray], lang: str) -> List[Tuple[str, float]]:
    # Prepare crops for device manager
    encoded_crops = [encode_tensor(resize_with_padding(crop)) for crop in crops]
    batch_size = self.batch_sizes.get(lang, 8)

    response = await self.client.infer(
        self.detection_model_path,  # Use detection path as model key
        {
            "mode": "recognition",
            "language": lang,
            "crops": encoded_crops,
            "batch_size": batch_size,
        },
        model_type="ocr",
    )

    # Decode batch results
    batch_raw_results = response["result"]  # List of encoded tensors
    results = []
    for raw_tensor in batch_raw_results:
        raw_result = decode_tensor(raw_tensor)
        decoded = ocr_eval_postprocess(raw_result)[0]
        results.append(decoded)

    return results
```

### 6. Update Service Cleanup

**File:** [system_services/hailo-ocr/hailo_ocr_server.py](system_services/hailo-ocr/hailo_ocr_server.py)  
**Location:** Shutdown handler in `start_server()` (lines ~426-430)  

```python
async def on_shutdown(app):
    if ocr_service and ocr_service.client:
        await ocr_service.client.disconnect()
```

### 7. Update Documentation

**Files:**  
- [system_services/hailo-ocr/ARCHITECTURE.md](system_services/hailo-ocr/ARCHITECTURE.md) - Update to reflect Group A architecture  
- [device_manager/ARCHITECTURE.md](device_manager/ARCHITECTURE.md) - Document OcrHandler  
- [device_manager/API_SPEC.md](device_manager/API_SPEC.md) - Add OCR to supported model types  

## Verification

### 1. Unit Tests
- Device manager: `python3 -m pytest device_manager/test_device_manager_concurrency.py`  
- OCR service: `python3 -m pytest system_services/hailo-ocr/tests/` (if exists)  

### 2. Integration Tests
- Health check: `curl http://localhost:11436/health` → `{"status": "ok", "models_loaded": true}`  
- OCR extraction: `curl -X POST http://localhost:11436/v1/ocr/extract -d '{"image": "data:image/jpeg;base64,...", "languages": ["en"]}'` → Verify text output  
- Models endpoint: `curl http://localhost:11436/models` → Verify loaded status  

### 3. Functional Tests
- **Batching edge cases:** Test with 1, 8, 15 regions  
- **Multi-language:** Test Chinese recognition (`languages: ["zh"]`)  
- **Concurrent services:** Run with hailo-vision simultaneously  
- **Error handling:** Invalid images, unsupported languages  

### 4. Performance Benchmark
- Compare latency vs current implementation (target: ~200-400ms per image)  
- Measure memory usage (should be similar)  
- Test throughput with concurrent requests  

## Decisions

### Unified OcrHandler vs Separate Handlers
**Chosen:** Unified `OcrHandler` with mode routing (detection/recognition).  
**Rationale:** Follows CLIP's multi-model pattern. Keeps coordination logic centralized. Simpler service code.  
**Alternative:** Separate `OcrDetectionHandler` and `OcrRecognitionHandler` - would require service to manage two model types and duplicate config logic.  

### Batching Location
**Chosen:** Device manager handler performs batching internally.  
**Rationale:** Matches hailo-apps pattern. Keeps NPU optimization logic in device manager. Service sends all crops in one call.  
**Alternative:** Service-side batching with multiple `infer()` calls - adds network overhead and complicates error handling.  

### Preserve Hailo-Apps Utilities
**Chosen:** Keep using `det_postprocess()`, `resize_with_padding()`, `ocr_eval_postprocess()`, `OcrCorrector`.  
**Rationale:** Proven, optimized utilities. No need to reimplement. Device manager handles NPU inference only; CPU-bound pre/post stays in service.  

## Rollback Plan

If issues arise:
1. Current callback-bridged implementation works and can remain  
2. No urgent need to migrate - this is architectural improvement, not bug fix  
3. Revert by checking out `hailo_ocr_server.py` from current commit  
4. Device manager changes are additive (new handler) - can disable by removing from registry  

## Dependencies

- Device manager must be running: `sudo systemctl start hailo-device-manager`  
- Models must be available at configured paths  
- No new Python dependencies required  

## Timeline

- **Phase 1:** Device manager handler (2-3 hours)  
- **Phase 2:** Service refactor (2-3 hours)  
- **Phase 3:** Testing & validation (1-2 hours)  
- **Phase 4:** Documentation (30 min)  

**Total:** 7-10 hours  

## Success Criteria

- ✅ OCR service starts and loads models via device manager  
- ✅ Text extraction works correctly for various images  
- ✅ Batching handles edge cases (1, 8, 15+ regions)  
- ✅ Multi-language recognition works  
- ✅ Concurrent operation with other services  
- ✅ Performance equivalent to current implementation  
- ✅ No breaking changes to REST API  

---

**Status:** Ready for implementation  
**Next:** Begin with device manager handler implementation