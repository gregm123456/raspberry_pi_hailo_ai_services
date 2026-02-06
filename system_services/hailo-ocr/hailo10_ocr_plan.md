# Hailo-10H Accelerated OCR Service Plan (Raspberry Pi 5)

## Overview
Transform `hailo-ocr` from CPU-based PaddleOCR to a Hailo-10H NPU-accelerated service using the pipeline app infrastructure from hailo-apps. Deploy with an isolated venv in `/opt/hailo-ocr/venv`, vendor hailo-apps, and use two-stage HEF models (detection + recognition) running on Hailo-10H. Support English and Chinese language sets via separate HEF models, exposing language selection through REST API. Implement async inference using `HailoInfer` callbacks integrated with aiohttp endpoints. Download HEF models during installation from Hailo S3 buckets. Expect 2-3× throughput improvement over CPU (3-5 img/s vs 1-2 img/s) with lower thermal impact.

---

## Steps

### 1. Vendor hailo-apps
- Copy hailo-apps submodule to `/opt/hailo-ocr/vendor/hailo-apps` during install
- Add `__init__.py` files for importability
- Patch `defines.py` to redirect `RESOURCES_ROOT_PATH_DEFAULT` to `/var/lib/hailo-ocr/resources`
- Install vendored hailo-apps into venv

### 2. Create requirements.txt
- Pin: `aiohttp`, `pyyaml`, `pillow`, `numpy`, `opencv-python`
- Add `hailort` (if not in system-site-packages)
- Remove `paddleocr`
- Document that hailo_platform comes from system-site-packages

### 3. Download HEF models/resources in install.sh
- Detect Hailo arch: `hailortcli fw-control identify`
- Download for Hailo-10H from S3:
  - `ocr_det.hef` (detection)
  - `ocr.hef` (recognition, English)
  - Optional: `ocr_chinese.hef` (Chinese)
- Download `libocr_postprocess.so` (h10 arch)
- Copy `ocr_config.json` from hailo-apps to `/var/lib/hailo-ocr/resources/`
- Store models in `/var/lib/hailo-ocr/resources/models/hailo10h/`
- Set ownership: `chown -R hailo-ocr:hailo-ocr /var/lib/hailo-ocr/`

### 4. Rewrite hailo_ocr_server.py to use HailoInfer
- Import `HailoInfer` from vendored hailo-apps
- Create two `HailoInfer` instances: detection, recognition (batch_size=8)
- Load models at startup
- Implement async detection callback pattern
- Use `functools.partial()` for context in callbacks
- Replace PaddleOCR calls with async queue-based pipeline
- Preprocess: PIL Image → NumPy array → normalize
- Call C++ postprocess via ctypes

### 5. Update config.yaml for Hailo models
- Add `hailo_models` section:
  ```yaml
  hailo_models:
    detection_hef: "ocr_det.hef"
    recognition_hefs:
      en: "ocr.hef"
      zh: "ocr_chinese.hef"  # Optional
    batch_size_det: 1
    batch_size_rec: 8
    priority: 0
  ```
- Keep existing `ocr` section for thresholds
- Add `device: "/dev/hailo0"`
- Update `languages` to reference available HEF models

### 6. Implement multi-language support
- At startup, load all available recognition HEF models (English + Chinese)
- Map language codes to model instances
- In `/v1/ocr/extract`, accept `languages` parameter
- For multi-language, run detection once, then recognition per language
- Return language-tagged results

### 7. Update hailo-ocr.service systemd unit
- `ExecStart`: `/opt/hailo-ocr/venv/bin/python3 /opt/hailo-ocr/hailo_ocr_server.py`
- Add `MemoryMax=3G`, `CPUQuota=75%`
- Ensure service user is in `hailo` group
- Add `Restart=always`, `RestartSec=5`
- Keep XDG env vars

### 8. Create model resolution logic
- Helper `resolve_hef_path()` checks:
  - Config.yaml path
  - `/var/lib/hailo-ocr/resources/models/hailo10h/{model_name}.hef`
  - Vendored hailo-apps resource locations
- Use hailo-apps resource resolution if needed
- Validate model files at startup

### 9. Preserve REST API compatibility
- Keep endpoints: `GET /health`, `POST /v1/ocr/extract`, `POST /v1/ocr/batch`
- Update response: add `model_version`, `detection_model`, `recognition_model`, `inference_time_ms`
- Add `/models` endpoint: list loaded HEF models
- Health check reports NPU status

### 10. Update documentation
- README.md: Document Hailo-10H, model download, multi-language
- ARCHITECTURE.md: Two-stage pipeline, async pattern, memory budget
- API_SPEC.md: Update response examples
- TROUBLESHOOTING.md: NPU access, model download, language model issues

### 11. Create verify.sh
- Check `/dev/hailo0` access
- Verify HEF models: `ls -lh /var/lib/hailo-ocr/resources/models/hailo10h/`
- Test systemd service: `systemctl is-active hailo-ocr`
- Health check: `curl http://localhost:11436/health`
- Test OCR inference (English/Chinese)
- Measure inference time
- Check logs: `journalctl -u hailo-ocr.service -n 50`

### 12. Update install.sh for Hailo workflow
- Prerequisite: `hailortcli fw-control identify`
- Create `/opt/hailo-ocr/` structure
- Create venv: `python3 -m venv --system-site-packages /opt/hailo-ocr/venv`
- Vendor hailo-apps (copy + patch + install)
- Download HEF models
- Install requirements
- Copy server/config renderer
- Install systemd unit, create user/group, set permissions
- Add service user to `hailo` group
- Optional `--warmup-models` flag

---

## Verification
1. Run `sudo ./install.sh --warmup-models`
2. Check service: `sudo systemctl status hailo-ocr.service`
3. Verify venv: `ls -la /opt/hailo-ocr/venv/lib/python3.*/site-packages/ | grep hailo`
4. Check models: `curl http://localhost:11436/models | jq`
5. Test English OCR: `curl -X POST http://localhost:11436/v1/ocr/extract -H "Content-Type: application/json" -d '{"image": "<base64>", "languages": ["en"]}'`
6. Test Chinese OCR: same with `"languages": ["zh"]`
7. Verify NPU: `sudo cat /sys/class/hailo_chardev/hailo0/device/power_measurement`
8. Benchmark: 10 images sequentially (<3s total)
9. Check memory: `ps aux | grep hailo-ocr`
10. Check logs: `sudo journalctl -u hailo-ocr.service -n 50`

---

## Decisions
- **Pipeline app over standalone:** Use pipeline app for better integration
- **Multi-language via separate HEF models:** Each language = separate recognition model
- **Venv + vendoring:** Matches hailo-vision pattern
- **Pre-load models at startup:** Avoids cold-start penalty
- **Batch size 8 for recognition:** Efficient NPU utilization
- **Memory budget 3 GB:** Fits Pi 5 with other services
- **Keep REST API shape:** Backwards compatible
- **Chinese language conditional:** Install English by default; Chinese optional

---

## Lessons Learned
1. **Device manager socket errors are transient:** No need to worry about them; they resolve automatically as services connect.
2. **Model file permissions must be accessible by device_manager:** Ensure downloaded HEF models have permissions allowing the device manager (running as `hailo-device-mgr` user) to read them. Typically, set group permissions to `hailo-device-mgr:hailo-ocr` with 640 permissions.
3. **Testing practices:** When ready to test the new service, uninstall the old service (and its config) first. Test against the running system service, and do NOT put raw base64 in curl commands or in test output—use file payloads or script the base64 encoding to avoid cluttering logs and conversations.
