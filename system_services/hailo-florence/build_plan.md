# Hailo-Florence Service Productionization Build Plan

## Overview

This document details the comprehensive plan to rework the hailo-florence prototype into a robust, supportable systemd service for the Raspberry Pi 5 + Hailo-10H platform. The service will provide image captioning and visual question answering (VQA) via a REST API, using Hailo-accelerated models for all vision components. The plan follows proven patterns from other system_services (hailo-clip, hailo-whisper, etc.) and incorporates all best practices for deployment, configuration, and maintainability.

---

## 1. Goals & Scope

- **Primary Tasks:**
	- Image Captioning (single-image, 512x512 typical)
	- Visual Question Answering (VQA)
- **API:** REST, JSON, standard error formats, port 11438
- **Model Execution:** All vision components (encoder) must run on Hailo-10H (no CPU fallback)
- **Deployment:** Python venv in /opt/hailo-florence/, systemd-managed, persistent model loading
- **Config:** YAML user config rendered to JSON for runtime
- **Documentation:** Complete, following system_services standards

---

## 2. Reference Patterns & Architecture

### Directory Structure

```
system_services/hailo-florence/
├── README.md
├── API_SPEC.md
├── ARCHITECTURE.md
├── TROUBLESHOOTING.md
├── config.yaml
├── hailo_florence_service.py
├── render_config.py
├── hailo-florence.service
├── install.sh
├── uninstall.sh
├── verify.sh
├── requirements.txt
└── tests/
		├── conftest.py
		├── test_service.py
		└── test_api.py
```

### Installer Pattern (install.sh)

1. Validate prerequisites (root, Hailo driver, Python 3.10+, disk space)
2. Create system user/group (hailo-florence)
3. Set device permissions (add user to Hailo group)
4. Setup directories: /opt/hailo-florence/, /var/lib/hailo-florence/, /etc/hailo/, /etc/xdg/florence/
5. Vendor hailo-apps/ into /opt/hailo-florence/vendor/
6. Create Python venv in /opt/hailo-florence/venv (with --system-site-packages)
7. Install requirements.txt into venv
8. Download models:
	 - Florence-2 encoder HEF
	 - Florence-2 decoder HEF
	 - Tokenizer (from Hugging Face)
9. Store models in /var/lib/hailo-florence/models/
10. Render config.yaml → /etc/xdg/florence/florence.json
11. Install systemd unit, reload, enable, start
12. Run verify.sh for post-install checks

### Systemd Unit Pattern

Standardized, minimal, with resource limits and XDG environment variables. See plan for full example.

### API Design Pattern

- REST, JSON, standard HTTP status codes
- Endpoints:
	- GET /health
	- POST /v1/caption
	- POST /v1/vqa
	- GET /metrics (optional)
- Accepts images as base64 or multipart/form-data
- Standardized error responses

### Model Management

- Persistent model loading on startup
- All models (encoder, decoder, tokenizer) loaded into memory
- Graceful unload on SIGTERM

---

## 3. Implementation Steps

### 3.1. Vision Encoder Implementation

- Locate Hailo-10H-accelerated Florence-2 vision encoder in hailo-apps/ or hailo-rpi5-examples/
- Confirm HEF model availability for encoder and decoder
- Extract and adapt reference pipeline code for Hailo-accelerated inference
- Document exact model file names and download sources

### 3.2. Directory & File Structure

- Create all files and folders as per the reference structure above
- Ensure all scripts are idempotent and safe for repeated runs

### 3.3. install.sh (Idempotent Installer)

- Validate environment (root, Hailo driver, Python, disk)
- Create user/group, set device permissions
- Setup all required directories
- Vendor hailo-apps/
- Create venv, install requirements
- Download and place models (HEF, tokenizer)
- Render config
- Install and enable systemd unit
- Run verify.sh

### 3.4. hailo_florence_service.py (FastAPI Server)

- Load config from /etc/xdg/florence/florence.json
- FlorencePipeline class:
	- Load encoder/decoder HEFs, tokenizer on startup
	- Methods: caption(image), vqa(image, question)
	- Preprocess images (resize, normalize)
	- Persistent model loading
- FastAPI endpoints:
	- /health: service/model status
	- /v1/caption: POST, returns caption
	- /v1/vqa: POST, returns answer
	- /metrics: GET, Prometheus format (optional)
- Structured logging to journald
- Graceful shutdown (SIGTERM handler)

### 3.5. render_config.py

- Convert YAML config to JSON for runtime
- Validate required fields
- Idempotent, safe to rerun

### 3.6. hailo-florence.service (systemd unit)

- User/group: hailo-florence
- WorkingDirectory: /var/lib/hailo-florence
- ExecStart: /opt/hailo-florence/venv/bin/python3 /opt/hailo-florence/hailo_florence_service.py
- Environment: XDG_CONFIG_HOME, XDG_DATA_HOME, PYTHONUNBUFFERED
- Resource limits: MemoryMax=3G, CPUQuota=70%
- Restart policies, timeouts

### 3.7. config.yaml (User Config Template)

- Port: 11438
- Model paths (encoder_hef, decoder_hef, tokenizer_path)
- Inference params (max_length, num_beams, temperature, image_size)

### 3.8. Documentation

- README.md: overview, quick start, config
- API_SPEC.md: endpoints, request/response, curl examples
- ARCHITECTURE.md: design, model selection, resource analysis
- TROUBLESHOOTING.md: common issues, diagnostics

### 3.9. Testing

- tests/test_service.py: unit tests for pipeline
- tests/test_api.py: integration tests for REST API
- verify.sh: systemd status, /health, /v1/caption, /v1/vqa checks

### 3.10. uninstall.sh

- Stop and disable service
- Remove all files, user/group
- Clean up config and data directories

### 3.11. requirements.txt

- Pin all dependencies for Pi 5 compatibility

---

## 4. Verification Checklist

1. Installer runs cleanly (`sudo ./install.sh`)
2. Service is active (`systemctl status hailo-florence`)
3. API responds (`curl http://localhost:11438/health`)
4. Captioning works (`/v1/caption`)
5. VQA works (`/v1/vqa`)
6. Logs accessible via journald
7. All tests pass (pytest, verify.sh)

---

## 5. Key Decisions

- Vision encoder must be Hailo-10H accelerated (no CPU fallback)
- Phase 1: Captioning + VQA only, single-image API
- Port: 11438
- Persistent model loading
- YAML→JSON config flow
- venv in /opt/hailo-florence/ with --system-site-packages
- Standardized error responses

---

## 6. Future Extensions (Phase 2+)

- Add more Florence tasks (object detection, OCR, segmentation, region/dense captioning)
- Batch and streaming endpoints
- Prometheus metrics, Grafana dashboards
- Health-check based auto-recovery

---

## 7. References

- See hailo-clip, hailo-whisper, hailo-vision, hailo-pose, hailo-ocr for proven patterns
- Reference implementation: hailo-rpi5-examples/community_projects/dynamic_captioning/
- Model sources: Hailo S3, Hugging Face

---

**End of build plan.**
