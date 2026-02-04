# Hailo Whisper Service Rework Plan

Goal: Rework the hailo-whisper prototype into a supportable, production-style system service following the patterns in hailo-pose, hailo-vision, hailo-ocr, and hailo-clip. The service must be OpenAI Whisper API compatible, install into an isolated /opt venv, download required models during install, and integrate cleanly with systemd and XDG config paths.

## Guiding Principles

- Use existing standards (OpenAI Whisper API) and avoid custom endpoints.
- Follow the established service patterns (installer, venv, vendored hailo-apps, XDG config, systemd hardening).
- Keep models loaded by default for low latency; support keep_alive for unload behavior.
- Make install scripts idempotent and safe to rerun.
- Prefer hailo-apps for resource acquisition and model resolution.
- Keep docs complete and consistent with actual behavior.

## Decisions (Confirmed)

- API compatibility: OpenAI Whisper only.
- Default model: whisper-small-int8 only.
- Model acquisition: hailo-apps download_resources.
- Default port: 11437 (avoid conflicts with OCR and Pose).

## Phase 1: Align Service Layout with Proven Patterns

### 1.1 Directory and Runtime Layout

Target layout (matching hailo-pose and hailo-vision):

- /opt/hailo-whisper/
  - venv/
  - vendor/hailo-apps/
  - hailo_whisper_server.py
  - render_config.py
  - requirements.txt
- /var/lib/hailo-whisper/
  - resources/
    - models/hailo10h/
  - cache/
- /etc/hailo/hailo-whisper.yaml
- /etc/xdg/hailo-whisper/hailo-whisper.json
- /etc/systemd/system/hailo-whisper.service

### 1.2 Service User, Permissions, and Device Access

- Create service user and group: hailo-whisper.
- Add hailo-whisper to the /dev/hailo0 device group.
- Ensure /var/lib/hailo-whisper is owned by hailo-whisper:hailo-whisper.
- Ensure /opt/hailo-whisper is readable by service user.

## Phase 2: Installer Rework (install.sh)

Rework the installer to match the hailo-pose flow in
system_services/hailo-pose/install.sh.

### 2.1 Preflight Checks

- Verify root execution.
- Validate /dev/hailo0 exists.
- If hailortcli is available, run hailortcli fw-control identify.
- Verify HailoRT python bindings (hailo_platform) in system site-packages.
- Verify python3 is present.
- Verify hailo-apps submodule exists.

### 2.2 Create Venv in /opt

- python3 -m venv --system-site-packages /opt/hailo-whisper/venv
- pip install -r requirements.txt

### 2.3 Vendor hailo-apps

- Copy hailo-apps into /opt/hailo-whisper/vendor/hailo-apps
- Patch RESOURCES_ROOT_PATH_DEFAULT to /var/lib/hailo-whisper/resources
- Add missing __init__.py files (consistent with pose/vision)
- Install vendored hailo-apps into venv

### 2.4 Install Config and Render JSON

- Copy config.yaml to /etc/hailo/hailo-whisper.yaml if missing.
- Render JSON to /etc/xdg/hailo-whisper/hailo-whisper.json using render_config.py.

### 2.5 Download Whisper Model

- Use hailo_apps.installation.download_resources:
  - group: whisper (confirm exact group in hailo-apps)
  - arch: hailo10h
  - resource-type: model
  - resource-name: whisper-small-int8
- Verify HEF exists in /var/lib/hailo-whisper/resources/models/hailo10h.
- Set ownership to hailo-whisper:hailo-whisper.

### 2.6 Install Systemd Unit and Start

- Install unit to /etc/systemd/system/hailo-whisper.service
- systemctl daemon-reload
- systemctl enable --now hailo-whisper.service
- Optional warmup flag to hit /health or /health/ready

## Phase 3: Systemd Unit Standardization

Update hailo-whisper.service to match patterns from hailo-pose:

- ExecStart should call venv python:
  /opt/hailo-whisper/venv/bin/python3 /opt/hailo-whisper/hailo_whisper_server.py
- Set WorkingDirectory=/var/lib/hailo-whisper
- Set StateDirectory=hailo-whisper
- XDG vars:
  - XDG_CONFIG_HOME=/etc/xdg
  - XDG_CONFIG_DIRS=/etc/xdg
  - XDG_DATA_HOME=/var/lib
  - XDG_DATA_DIRS=/var/lib:/usr/share:/usr/local/share
- Set HAILO_PRINT_TO_SYSLOG=1
- Restart policy: Restart=always, RestartSec=5, TimeoutStopSec=30, KillSignal=SIGTERM
- Resource limits from config.yaml (MemoryMax, CPUQuota)
- Hardening:
  - PrivateTmp=yes
  - NoNewPrivileges=yes
  - ProtectSystem=strict
  - ProtectHome=yes
  - ReadWritePaths=/var/lib/hailo-whisper /etc/xdg/hailo-whisper

## Phase 4: Replace Prototype Inference with Real Pipeline

### 4.1 Service Config

- Load JSON config from /etc/xdg/hailo-whisper/hailo-whisper.json.
- Ensure defaults are consistent with config.yaml.
- Respect keep_alive behavior.
- Default language can be null to enable auto-detect, but keep YAML default as en.

### 4.2 Model Loading and Lifecycle

- Use hailo-apps or HailoRT wrappers to load Whisper HEF at startup.
- Persist model in memory when keep_alive=-1.
- Allow optional unload for keep_alive=0 or timed unload in the service.

### 4.3 Audio Processing Pipeline

Implement a real pipeline aligned to Hailo-Whisper usage:

- Decode incoming audio with ffmpeg or soundfile.
- Convert to 16kHz mono PCM.
- Enforce max duration and size limits.
- Generate mel-spectrogram features.
- Run encoder + decoder on Hailo NPU.
- Postprocess tokens to text.
- Optionally apply VAD filtering (config-driven).

### 4.4 API Compatibility

Keep strict OpenAI Whisper compatibility:

- POST /v1/audio/transcriptions
- GET /v1/models
- GET /health
- GET /health/ready

Return formats:
- json, verbose_json, text, srt, vtt

Match error response format in API_SPEC.md:

{
  "error": {"message": "...", "type": "invalid_request_error"}
}

### 4.5 Response Formatting

- Implement correct timestamp formatting for SRT and VTT.
- Provide segment metadata in verbose_json.
- Ensure text-only response when response_format=text.

## Phase 5: Configuration Updates

### 5.1 Default Port

- Change default port to 11437 in config.yaml.
- Update install.sh default port logic.
- Update README.md, API_SPEC.md, TROUBLESHOOTING.md.

### 5.2 Resource Paths

- Ensure cache_dir is /var/lib/hailo-whisper/cache.
- Ensure resources are in /var/lib/hailo-whisper/resources.

## Phase 6: Documentation and Support Files

Update docs to match real behavior and new runtime layout:

- README.md: mention venv in /opt, model download, default port 11437.
- API_SPEC.md: ensure endpoints and examples use 11437.
- ARCHITECTURE.md: update component diagram, resource layout, and pipeline steps.
- TROUBLESHOOTING.md: add model download failures, hailo-apps missing, port conflicts.
- Verify that all docs align to OpenAI Whisper compatibility only.

## Phase 7: Verify and Validate

### 7.1 Automated Checks

- Run install.sh and verify systemd status.
- Run verify.sh (update as needed).

### 7.2 Manual Checks

- curl http://localhost:11437/health
- curl http://localhost:11437/health/ready
- curl http://localhost:11437/v1/models
- Transcribe a short WAV file and compare response format to API_SPEC.

### 7.3 Resource Monitoring

- Confirm memory usage stays within MemoryMax.
- Verify logs show model load and inference stats.

## Risks and Mitigations

- Model group/name mismatch in hailo-apps:
  - Mitigation: confirm hailo-apps group name for Whisper, update installer accordingly.
- Audio preprocessing dependencies missing:
  - Mitigation: pin requirements.txt and install via venv; document dependencies.
- Port conflict with existing services:
  - Mitigation: default to 11437 and warn if in use.

## Deliverables

- Updated hailo-whisper install.sh with venv + vendored hailo-apps + model download.
- Updated hailo-whisper.service with XDG wiring and hardening.
- Updated hailo_whisper_server.py with real pipeline integration.
- Updated config.yaml defaults (port 11437) and render_config.py usage.
- Updated README.md, API_SPEC.md, ARCHITECTURE.md, TROUBLESHOOTING.md.
- Updated verify.sh to check new port and model availability.

## Out of Scope (For Later)

- Streaming transcription (WebSocket).
- Translation endpoint.
- Multi-model switching per request.
- Prometheus metrics endpoint.

## Work Order Summary

1. Rework installer to match hailo-pose pattern and create /opt venv.
2. Vendor hailo-apps and patch resource path to /var/lib/hailo-whisper/resources.
3. Implement model download for whisper-small-int8 via hailo-apps.
4. Update systemd unit to venv ExecStart and full XDG wiring.
5. Replace placeholder Whisper logic with real hailo-apps inference pipeline.
6. Update configs and docs to default port 11437.
7. Validate with verify.sh and curl checks.
