# hailo-pose System Service Build Plan

## Overview

This plan details the steps to transform the hailo-pose prototype into a production-ready, supportable system service for pose estimation on the Hailo-10H NPU (Raspberry Pi 5). It follows established patterns from hailo-clip, hailo-ocr, and hailo-vision, including isolated Python venv deployment, model acquisition, systemd integration, and robust documentation.

---

## 1. Requirements.txt
- Create `requirements.txt` in `system_services/hailo-pose/`
- Include:
  - `aiohttp==3.11.11`
  - `pyyaml==6.0.2`
  - `pillow==11.1.0`
  - `numpy==1.26.4`
  - `opencv-python==4.11.0.86`
- Do NOT include hailo-apps; it will be vendored and installed separately.

---

## 2. Installer Script (install.sh)
- Rewrite `install.sh` to follow hailo-vision pattern:
  1. **Prerequisites:**
     - Check `/dev/hailo0` exists
     - Run `hailortcli fw-control identify` to verify NPU
     - Ensure `python3-h10-hailort` is installed
  2. **User/Group:**
     - Create `hailo-pose` user/group
     - Add user to device group (`stat -c '%G' /dev/hailo0`)
  3. **Directories:**
     - `/opt/hailo-pose/` (venv, vendor)
     - `/var/lib/hailo-pose/resources/models/hailo10h/`, `/var/lib/hailo-pose/cache/`
     - `/etc/hailo/`, `/etc/xdg/hailo-pose/`
  4. **Python venv:**
     - `python3 -m venv --system-site-packages /opt/hailo-pose/venv`
     - `venv/bin/pip install --upgrade pip`
     - `venv/bin/pip install -r requirements.txt`
  5. **Vendor hailo-apps:**
     - Copy `../../hailo-apps` to `/opt/hailo-pose/vendor/hailo-apps`
     - Patch `defines.py` to set `RESOURCES_ROOT_PATH_DEFAULT = "/var/lib/hailo-pose/resources"`
     - `venv/bin/pip install vendor/hailo-apps`
  6. **Model Download:**
     - Use hailo-apps download logic or direct download for `yolov8s_pose.hef` to `/var/lib/hailo-pose/resources/models/hailo10h/`
  7. **Config:**
     - Install `config.yaml` to `/etc/hailo/hailo-pose.yaml`
     - Render JSON: `python3 render_config.py --input /etc/hailo/hailo-pose.yaml --output /etc/xdg/hailo-pose/hailo-pose.json`
  8. **systemd Unit:**
     - Install `hailo-pose.service` to `/etc/systemd/system/`
     - `systemctl daemon-reload && systemctl enable --now hailo-pose.service`
  9. **Warmup Option:**
     - Support `--warmup` flag to pre-load model and validate install

---

## 3. Systemd Unit (hailo-pose.service)
- Update `ExecStart` to:
  - `/opt/hailo-pose/venv/bin/python3 /opt/hailo-pose/hailo_pose_service.py`
- Add environment variables:
  - `XDG_CONFIG_HOME=/etc/xdg`
  - `XDG_DATA_HOME=/var/lib`
  - `XDG_DATA_DIRS=/var/lib:/usr/share:/usr/local/share`
  - `HAILO_PRINT_TO_SYSLOG=1`
  - `PYTHONUNBUFFERED=1`
- Set resource limits:
  - `MemoryMax=2G`
  - `CPUQuota=80%`
- Set working directory and writable paths:
  - `WorkingDirectory=/var/lib/hailo-pose`
  - `ReadWritePaths=/var/lib/hailo-pose /etc/xdg/hailo-pose`

---

## 4. Service Implementation (hailo_pose_service.py)
- Update imports:
  - `HailoInfer`, `resolve_hef_path`, `default_preprocess`, pose utils
- Implement model lifecycle:
  - **initialize():**
    - Use `resolve_hef_path("yolov8s_pose", "pose_estimation", "hailo10h")`
    - Initialize `HailoInfer` and post-processor
    - Get model input shape
  - **detect_poses():**
    - Preprocess image with `default_preprocess` (letterbox + padding)
    - Run inference and post-process results
    - Map results to COCO format JSON response
  - **shutdown():**
    - Release NPU resources
- Load config from JSON (`/etc/xdg/hailo-pose/hailo-pose.json`)

---

## 5. Deployment
- Copy service files to `/opt/hailo-pose/`
- Ensure proper ownership (`chown -R hailo-pose:hailo-pose ...`)

---

## 6. Uninstaller (uninstall.sh)
- Remove `/opt/hailo-pose/`, `/var/lib/hailo-pose/`, `/etc/xdg/hailo-pose/`
- Optionally remove `/etc/hailo/hailo-pose.yaml`

---

## 7. Documentation Updates
- Update `ARCHITECTURE.md` with:
  - HailoInfer integration
  - Preprocessing strategy
  - Resource paths and vendoring
  - Memory/concurrency notes
- Update `TROUBLESHOOTING.md` with:
  - Model download issues
  - venv setup requirements
  - Device access errors
  - Inference errors

---

## 8. Verification
- Run installer: `sudo ./install.sh --warmup`
- Check service: `systemctl status hailo-pose`
- View logs: `journalctl -u hailo-pose -f`
- Test API: `curl -X POST http://localhost:8084/v1/pose/detect -F "image=@test_image.jpg"`
- Run tests: `pytest tests/test_hailo_pose_service.py`
- Monitor resource usage and concurrency

---

## Decisions
- **Model:** Use `yolov8s_pose` (optimized for Hailo-10H)
- **Preprocessing:** Letterbox with padding (hailo-apps default)
- **Warmup:** Include installer `--warmup` option
- **Resource allocation:** Use conservative systemd limits
- **Config format:** JSON (rendered from YAML)

---

## Notes
- All steps follow project standards for maintainability and supportability.
- Reference implementations: hailo-clip, hailo-ocr, hailo-vision.
- See `ARCHITECTURE.md` and `API_SPEC.md` for further details.
