# Device Manager Integration Phase 1: Hailo-Clip + Hailo-Vision

**Date:** February 5, 2026  
**Author:** Greg  
**Status:** Draft Plan  

## Overview

This plan outlines the careful, phased integration of the **device_manager** feature from the `device-manager` branch into the current `main` branch. The goal is to enable concurrent AI services on the Hailo-10H NPU by introducing a centralized device manager that serializes inference requests, preventing device access conflicts.

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
- Install script runs: `./device_manager/install.sh --help`

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

## Next Phases

**Phase 2:** Roll out to hailo-ocr, hailo-depth, hailo-pose (HailoInfer services).

**Phase 3:** Update remaining services and documentation.

**Phase 4:** Full integration testing with all services concurrent.</content>
<filePath>/home/gregm/raspberry_pi_hailo_ai_services/PLAN_device_manager_integration_phase_1.md
