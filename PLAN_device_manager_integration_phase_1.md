# Device Manager Integration Phase 1: Hailo-Clip + Hailo-Vision

**Date:** February 5, 2026  
**Author:** Greg  
**Status:** Step 3 Complete & Validated (Feb 5, 2026) - hailo-clip and hailo-vision using device manager, smoke tests passed.

**Phase 1 Scope (Low Risk):**
- Integrate only the `device_manager/` folder and its dependencies.
- Update only `hailo-clip` and `hailo-vision` services to use the new `HailoDeviceClient` pattern.
- Preserve all main-branch improvements (port changes, config updates, install script enhancements).
- Defer other services, documentation updates, and broader changes until Phase 1 is validated.

**Why This Approach:**
- `hailo-clip` and `hailo-vision` are production-ready services with direct `VDevice` usage.
- Starting small minimizes risk and allows validation of the device manager pattern.
- Main branch has evolved (e.g., default ports, configs); we want to keep those improvements.
- Device manager enables true concurrency: multiple services can run simultaneously without crashes.

**Expected Outcome:**
- `hailo-clip` and `hailo-vision` can run concurrently, sharing the Hailo-10H device via the device manager.
- No breaking changes to existing APIs or configurations.
- Foundation for rolling out to other services in future phases.

## Prerequisites

Before starting:
1. **Git Access:** Ensure you have access to the `device-manager` branch (contains the full device manager code).
2. **Current State:** Working `main` branch with `hailo-clip` and `hailo-vision` services installed and tested individually.
3. **Hardware:** Raspberry Pi 5 with Hailo-10H AI HAT+ 2, Hailo driver installed (`hailortcli fw-control identify` works).
4. **Backup:** Commit or stash any uncommitted changes in `main`.
5. **Testing Environment:** Ability to run services on actual hardware for validation.
6. **Clean Slate:** Uninstall existing hailo-clip and hailo-vision services to avoid conflicts during integration. Also stop any other running hailo-* services to prevent device conflicts:
   ```bash
   sudo ./system_services/hailo-clip/uninstall.sh
   sudo ./system_services/hailo-vision/uninstall.sh
   sudo systemctl stop hailo-*  # Stop all other hailo services
   ```

## Step-by-Step Implementation

### Step 1: Bring in Device Manager Code

**Objective:** Copy the complete `device_manager/` folder from the `device-manager` branch into `main`, replacing the empty placeholder.

**Why:** The `device-manager` branch has the full implementation (`hailo_device_manager.py`, `device_client.py`, etc.). Main currently has an empty `device_manager/` folder.

**Steps:**
1. Checkout the `device-manager` branch temporarily:
   ```bash
   git checkout device-manager
   ```

2. Copy the entire `device_manager/` folder to a temporary location:
   ```bash
   cp -r device_manager /tmp/device_manager_backup
   ```

3. Switch back to `main`:
   ```bash
   git checkout main
   ```

4. Replace the empty `device_manager/` with the backed-up version:
   ```bash
   rm -rf device_manager
   cp -r /tmp/device_manager_backup device_manager
   ```

5. Verify the contents:
   ```bash
   ls -la device_manager/
   ```
   Expected: `hailo_device_manager.py`, `device_client.py`, `hailo-device-manager.service`, `install.sh`, test files, docs.

6. Stage and commit:
   ```bash
   git add device_manager/
   git commit -m "Phase 1: Integrate device_manager folder from device-manager branch"
   ```

**Validation:**
- No syntax errors: `python3 -m py_compile device_manager/*.py`
- Install script runs: `sudo ./device_manager/install.sh --help`

### Step 2: Update Hailo-Clip Service for Device Manager

**Objective:** Modify `hailo_clip_service.py` to use `HailoDeviceClient` instead of direct `VDevice` access, while preserving main-branch improvements.

**Key Changes:**
- Replace `VDevice` creation with `HailoDeviceClient` async context manager.
- Update model loading/inference to use client methods.
- Keep existing config, ports, and API unchanged.

**Steps:**
1. Examine current `hailo_clip_service.py` (main version) and compare with device-manager branch version.

2. In `hailo_clip_service.py`, update imports:
   ```python
   # Add after existing Hailo imports
   from device_client import HailoDeviceClient
   ```

3. Modify `CLIPModel.__init__` and `load()`:
   - Remove direct `VDevice` creation.
   - Add async context for device client.

4. Update `encode_image()` and `encode_text()`:
   - Replace `self.vdevice.create_infer_model()` calls with `await client.load_model()` and `await client.infer()`.

5. Update `CLIPServiceConfig` and Flask app creation to handle async client.

6. Ensure backward compatibility: if device manager unavailable, fall back to mock mode.

**Specific Code Changes:**
- In `CLIPModel.load()`: Replace VDevice setup with async client initialization.
- In inference methods: Use `await client.infer(hef_path, input_data, model_type="clip")`.

**Validation:**
- Service starts: `python3 hailo_clip_service.py` (should use mock if device manager not running).
- API tests: Health check and classify endpoint work.

### Step 3: Update Hailo-Vision Service for Device Manager

**Objective:** Modify `hailo_vision_server.py` to use `HailoDeviceClient` instead of direct `VDevice` access.

**Key Changes:**
- Similar to hailo-clip: replace `VDevice` with `HailoDeviceClient`.
- Update `VisionService.initialize()` and `process_image()` methods.
- Preserve OpenAI Chat Completions API compatibility.

**Steps:**
1. Compare main and device-manager versions of `hailo_vision_server.py`.

2. Add import: `from device_client import HailoDeviceClient`

3. Modify `VisionService.initialize()`:
   - Remove `VDevice` creation.
   - Use async client for model loading.

4. Update `process_image()`:
   - Replace direct inference with `await client.infer()`.

5. Ensure async handling in aiohttp handlers.

**Validation:**
- Service starts and loads model.
- Chat completions API works for image analysis.

**Completed (Feb 5, 2026):**
- ✓ Updated hailo_vision_server.py to use HailoDeviceClient instead of direct VDevice/VLM
- ✓ Added encode_tensor() helper function for base64 encoding numpy arrays
- ✓ Updated hailo-vision.service systemd unit with device manager dependencies
- ✓ Fixed model file permissions issue (chmod 644 on .hef, chmod 755 on directories)
- ✓ Service starts successfully and loads VLM model via device manager
- ✓ Health endpoint reports model_loaded: true
- ✓ Smoke test passed: Vision API processes images and returns responses (inference_time: ~3.8s)

### Step 4: Update Systemd Units for Dependencies

**Objective:** Ensure services start after device manager and depend on the socket.

**Changes:**
- Add `After=hailo-device-manager.service` to both service units.
- Add `Requires=hailo-device-manager.service` for hard dependency.
- Ensure socket path `/run/hailo/device.sock` is available.

**Steps:**
1. Edit `hailo-clip.service`:
   ```ini
   [Unit]
   After=network-online.target hailo-device-manager.service
   Requires=hailo-device-manager.service
   ```

2. Edit `hailo-vision.service` similarly.

3. Reload systemd: `sudo systemctl daemon-reload`

**Validation:**
- Services fail to start if device manager not running.
- Proper startup order: device manager → clip/vision.

### Step 5: Update Install Scripts

**Objective:** Modify install scripts to set up device manager alongside services.

**Changes:**
- In `hailo-clip/install.sh` and `hailo-vision/install.sh`:
  - Add check/install of device manager service.
  - Ensure socket permissions.
  - Keep existing venv, user, and config setup.

**Steps:**
1. In install scripts, add:
   ```bash
   # Install device manager if not present
   if ! systemctl is-enabled hailo-device-manager.service; then
       sudo ./device_manager/install.sh
   fi
   ```

2. Verify socket: `ls -la /run/hailo/device.sock`

**Validation:**
- Full install works: `./install.sh` sets up device manager + service.

### Step 6: Testing and Verification

**Objective:** Validate concurrent operation without conflicts.

**Steps:**
1. Install device manager: `sudo ./device_manager/install.sh`

2. Install and start services:
   ```bash
   sudo ./hailo-clip/install.sh
   sudo ./hailo-vision/install.sh
   sudo systemctl start hailo-device-manager hailo-clip hailo-vision
   ```

3. Run device manager tests: `cd device_manager && python3 -m pytest test_*.py`

4. Test concurrent inference:
   - Clip: `curl -X POST http://localhost:5000/v1/classify -d '{"image": "...", "prompts": ["cat", "dog"]}'`
   - Vision: `curl -X POST http://localhost:11435/v1/chat/completions -d '{"messages": [{"role": "user", "content": [{"type": "text", "text": "Describe this image"}, {"type": "image_url", "image_url": "..."}]}]}'`

5. Monitor logs: `journalctl -u hailo-device-manager -f`

6. Check memory/thermal: `free -h && vcgencmd measure_temp`

**Success Criteria:**
- Both services respond to API calls.
- No device conflicts in logs.
- Concurrent requests work (queueing visible in device manager logs).
- Memory usage <6GB total.

## Risks and Rollback

**Risks:**
- Device manager bugs cause service failures.
- Performance regression from IPC overhead.
- Socket permission issues.

**Rollback:**
- Stop services: `sudo systemctl stop hailo-clip hailo-vision hailo-device-manager`
- Revert commit: `git reset --hard HEAD~1`
- Reinstall services without device manager.

## Known Issues & Future Fixes

**Permission Fix Required for Model Files:**
- When hailo-vision downloads models to `/var/lib/hailo-vision/resources/models/`, they are created with restrictive permissions (600) and owned by the hailo-vision user.
- The device manager (running as hailo-device-manager user) cannot read these files, causing "HAILO_OPEN_FILE_FAILURE(13)" errors.
- **Fix Applied:** `sudo chmod 644` on model files and `sudo chmod 755` on parent directories to allow device manager read access.
- **Future:** Install script should set proper permissions automatically, or services should use a common group for model file access.

**Device Manager Install Script Socket Verification Race Condition:**
- The `device_manager/install.sh` script runs `systemctl restart hailo-device-manager` followed by an immediate socket verification check (`verify_service()`).
- Since systemd restart is asynchronous, the service may not have fully started by the time the socket check runs, causing a false "socket not created" error.
- **Fix:** Add a retry loop (with exponential backoff, max ~5 seconds) to `verify_service()` to poll for socket existence before failing.
- **Status:** Functional—the service does create the socket and runs correctly; the error is cosmetic (timing only). No blocking issue for Phase 1.

## Next Phases

**Phase 2:** Roll out to hailo-ocr, hailo-depth, hailo-pose (HailoInfer services).

**Phase 3:** Update remaining services and documentation.

**Phase 4:** Full integration testing with all services concurrent.

---

**Footnote: Hailo-Vision Device Manager Conversion Pattern**

For reference when converting other services, here are the specific code changes made to `hailo_vision_server.py` in Step 3:

1. **Imports:**
   ```python
   # Before:
   from hailo_platform import VDevice
   from hailo_platform.genai import VLM
   
   # After:
   from device_client import HailoDeviceClient
   ```

2. **VisionService.__init__:**
   ```python
   # Before:
   self.vdevice = None
   self.vlm = None
   
   # After:
   self.client: Optional[HailoDeviceClient] = None
   ```

3. **VisionService.initialize():**
   ```python
   # Before:
   params = VDevice.create_params()
   params.group_id = SHARED_VDEVICE_GROUP_ID
   self.vdevice = VDevice(params)
   self.vlm = VLM(self.vdevice, str(self.hef_path))
   
   # After:
   self.client = HailoDeviceClient()
   await self.client.connect()
   await self.client.load_model(str(self.hef_path), model_type="vlm_chat")
   ```

4. **VisionService.process_image():**
   ```python
   # Before:
   response_text = self.vlm.generate_all(prompt=prompt, frames=[preprocessed_image], ...)
   self.vlm.clear_context()
   
   # After:
   response = await self.client.infer(str(self.hef_path), {
       "prompt": prompt,
       "frames": [encode_tensor(preprocessed_image)],
       "temperature": temperature,
       "seed": seed,
       "max_generated_tokens": max_tokens,
   }, model_type="vlm_chat")
   response_text = response.get("result", "")
   ```

5. **VisionService.shutdown():**
   ```python
   # Before:
   if self.vlm: self.vlm.release()
   if self.vdevice: self.vdevice.release()
   
   # After:
   if self.client: await self.client.disconnect()
   ```

6. **Added helper function:**
   ```python
   def encode_tensor(array: np.ndarray) -> Dict[str, Any]:
       return {
           "dtype": str(array.dtype),
           "shape": list(array.shape),
           "data_b64": base64.b64encode(array.tobytes()).decode("ascii"),
       }
   ```

7. **Systemd unit dependencies:**
   ```ini
   [Unit]
   After=network-online.target hailo-device-manager.service
   Requires=hailo-device-manager.service
   ```

This pattern can be applied to other services by replacing direct VDevice/VLM usage with HailoDeviceClient calls.</content>
<filePath>/home/gregm/raspberry_pi_hailo_ai_services/PLAN_device_manager_integration_phase_1.md
