# Device Manager Integration Phase 1.5: Hailo-Whisper + Hailo-Florence

**Date:** February 5, 2026  
**Author:** Greg  
**Status:** Planned (Feb 5, 2026) - Draft plan for whisper + florence integration following successful Phase 1 (clip + vision).

**Phase 1.5 Scope (Low Risk Extension):**
- Integrate only `hailo-whisper` and `hailo-florence` services to use the new `HailoDeviceClient` pattern.
- Preserve all main-branch improvements (ports, configs, install scripts).
- Defer other services until Phase 2.
- Enable concurrent operation of all four Group A services (clip, vision, whisper, florence).

**Why This Approach:**
- `hailo-whisper` and `hailo-florence` are production-ready services with direct `VDevice` usage.
- Both follow similar patterns to clip/vision but with unique challenges (Whisper: GenAI wrapper; Florence: multi-model).
- Starting small minimizes risk and allows validation of device manager with different service architectures.
- Main branch has evolved; we want to keep those improvements.

**Expected Outcome:**
- All four Group A services (clip, vision, whisper, florence) can run concurrently, sharing the Hailo-10H device via the device manager.
- No breaking changes to existing APIs or configurations.
- Foundation for rolling out to remaining services in Phase 2.

## Prerequisites

Before starting:
1. **Phase 1 Complete:** `hailo-clip` and `hailo-vision` successfully integrated with device manager, smoke tests passed.
2. **Git Access:** Working `main` branch with device manager code from Phase 1.
3. **Current State:** `hailo-whisper` and `hailo-florence` services installed and tested individually.
4. **Hardware:** Raspberry Pi 5 with Hailo-10H AI HAT+ 2, Hailo driver installed (`hailortcli fw-control identify` works).
5. **Backup:** Commit or stash any uncommitted changes.
6. **Testing Environment:** Ability to run services on actual hardware for validation.
7. **Clean Slate:** Stop any running hailo-* services to prevent device conflicts during integration.

## Step-by-Step Implementation

### Phase 1.5a: Hailo-Whisper Integration

**Objective:** Modify `hailo_whisper_server.py` to use `HailoDeviceClient` instead of direct `VDevice` access, while preserving main-branch improvements.

**Key Changes:**
- Replace `VDevice` creation with `HailoDeviceClient` async context manager.
- Update model loading/inference to use client methods.
- Keep existing config, ports, and OpenAI Whisper API unchanged.

**Steps:**
1. In `hailo_whisper_server.py`, update imports:
   ```python
   from device_client import HailoDeviceClient
   ```

2. Modify `WhisperModelManager.__init__` and `load()`:
   - Remove direct `VDevice` creation.
   - Add async context for device client.

3. Update `transcribe()`:
   - Replace `Speech2Text.generate_all_segments()` calls with `await client.infer(hef_path, audio_data, model_type="whisper")`.
   - If `Speech2Text` wrapper incompatible, convert to lower-level `InferModel` pattern.

4. Update `unload()`:
   - Replace `self._vdevice.release()` with `await client.unload_model(hef_path)`.

5. Ensure backward compatibility: if device manager unavailable, fall back to mock mode.

**Specific Code Changes:**
- In `WhisperModelManager.load()`: Replace VDevice setup with async client initialization.
- In `transcribe()`: Use `await client.infer(hef_path, input_data, model_type="whisper")`.

**Validation:**
- Service starts: `python3 hailo_whisper_server.py` (should use mock if device manager not running).
- API tests: Health check and transcription endpoint work.

### Phase 1.5b: Hailo-Florence Integration (with Preliminary Cleanup)

**Objective:** Modify `hailo_florence_service.py` to use `HailoDeviceClient` instead of direct `VDevice` access.

**Key Changes:**
- Similar to whisper: replace `VDevice` with `HailoDeviceClient`.
- Update `FlorencePipeline.initialize()` and inference methods.
- Preserve REST API compatibility.

**Preliminary Steps (Florence-specific):**
1. Add VDevice release in `FlorencePipeline.cleanup()` method.
2. Convert `threading.Lock` to `asyncio.Lock` for async compatibility.

**Steps:**
1. Add import: `from device_client import HailoDeviceClient`

2. Modify `FlorencePipeline.load()`:
   - Remove `VDevice` creation.
   - Use async client for encoder and decoder model loading (multi-model support required).

3. Update `generate_caption()` and `vqa()`:
   - Replace encoder inference with `await client.infer(encoder_hef_path, input_data, model_type="florence_encoder")`.
   - Replace decoder autoregressive loop with `await client.infer(decoder_hef_path, input_data, model_type="florence_decoder")`.

4. Update `cleanup()`:
   - Replace manual VDevice release with `await client.unload_model()` for both models.

**Validation:**
- Service starts and loads models.
- Caption and VQA APIs work.

### Phase 1.5c: Concurrent Service Validation

**Objective:** Ensure all four Group A services can run concurrently.

**Steps:**
1. Start all services: `sudo systemctl start hailo-device-manager hailo-clip hailo-vision hailo-whisper hailo-florence`

2. Verify health endpoints for all services.

3. Run concurrent requests to each service.

4. Monitor device manager logs for proper queue serialization.

**Validation:**
- All services active and healthy.
- Concurrent requests succeed.
- Device manager properly serializes inference requests.

## Verification

After completing all steps:

1. **Service Status:**
   ```bash
   systemctl status hailo-device-manager hailo-clip hailo-vision hailo-whisper hailo-florence
   # All should show active (running)
   ```

2. **Health Checks:**
   ```bash
   curl http://localhost:5000/health  # hailo-clip
   curl http://localhost:11435/health  # hailo-vision
   curl http://localhost:11437/health  # hailo-whisper
   curl http://localhost:11438/health  # hailo-florence
   # All should return 200 with model_loaded: true
   ```

3. **Concurrent Request Test:**
   ```bash
   # Terminal 1: Watch device manager logs
   journalctl -u hailo-device-manager -f
   
   # Terminal 2: Fire concurrent requests
   curl -X POST http://localhost:5000/v1/classify -d '...' &  # CLIP
   curl -X POST http://localhost:11435/v1/chat/completions -d '...' &  # Vision
   curl -X POST http://localhost:11437/v1/audio/transcriptions -F '...' &  # Whisper
   curl -X POST http://localhost:11438/v1/caption -d '...' &  # Florence
   
   # All should succeed; device manager logs should show queue serialization
   ```

4. **Integration Tests:** All existing test suites pass without modification

5. **Resource Usage:** Monitor memory consumption stays within systemd limits (`MemoryMax` not exceeded)

## Decisions

- **Whisper before Florence:** Whisper's async architecture and proper cleanup make it lower risk; Florence needs preliminary work
- **Florence multi-model challenge:** Requires device manager to support multiple leases per service—if not yet implemented, document as Phase 2 prerequisite or implement during Phase 1.5b
- **GenAI API wrapper handling:** If device manager doesn't support `Speech2Text` wrapper, convert Whisper to lower-level `InferModel` pattern like Florence
- **Threading → async conversion:** Florence's `threading.Lock` must convert to `asyncio.Lock` for clean device client integration; done as preliminary step to avoid mid-integration complexity

---

**Last Updated:** February 5, 2026  
**Reference:** See `PLAN_device_manager_integration_phase_1.md` for Phase 1 completion details