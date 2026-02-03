# Copilot Instructions: Raspberry Pi Hailo AI System Services

This repository provides individual system API services for AI applications running on the Hailo-10H NPU on a Raspberry Pi 5. These services are deployed as systemd services for persistent, managed operation.

## Project Overview

**Philosophy:** Build atop existing standards and protocols (Ollama API, standard REST conventions) to avoid reinventing the wheel. These are personal projects and art installations, not production systems—pragmatism over perfection.

**Architecture:** Modular system services for Hailo-10 AI acceleration on Raspberry Pi 5

**Target Environment:**
- Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- 64-bit Raspberry Pi OS (Trixie)
- systemd service management

**Structure:** `system_services/<service-name>/` mini-projects, each containing:
- Deployment scripts and installation logic
- Service configuration (systemd units)
- API/interface definitions
- Integration tests
- Documentation

## Service Examples

Each service wraps a specific AI capability as a managed systemd service. The **hailo-apps** submodule provides 20+ applications; we'll wrap them as services:

**hailo-ollama** (LLM inference) — *Starting point*:
- Wraps Ollama (proven LLM standard)
- Exposes Ollama-compatible REST API
- Manages model lifecycle, logging, health checks

**Future services** (vision, speech, etc.):
- **Object detection** — YOLO/SSD bbox detection API
- **Pose estimation** — YOLOv8 keypoint detection
- **Speech-to-text** — Whisper transcription API (Hailo-accelerated)
- **Text-to-speech** — Piper TTS synthesis API
- **OCR** — PaddleOCR text detection/recognition
- **Depth estimation** — Monocular/stereo depth maps
- **Face recognition** — Detection + embedding comparison
- Each adopts existing standards for that domain (Whisper API, COCO format, etc.)
- Same systemd patterns, tailored to service needs
- Pragmatic: works well on Pi 5, not over-engineered

## Coding Standards

### Python
- **Version:** 3.10+ (pragmatic balance between modern features and Raspberry Pi OS availability)
- **Style:** PEP 8 with type hints where they add clarity; don't over-engineer
- **Testing:** pytest for integration tests; quick manual verification acceptable for art/personal projects
- **Logging:** Python `logging` module; journald integration via systemd
- **Services:** Standard library `subprocess` or `systemctl` for management
- **Deployment:** Python services use isolated venvs in `/opt/hailo-service-name/venv` (see raspberry-pi skill for rationale)
- **Philosophy:** Favor existing, proven libraries over building from scratch (e.g., use Ollama directly rather than reimplementing inference)

### Bash
- **Style:** Follow `shellcheck` standards
- **Idempotency:** Scripts must be safe to run multiple times
- **Error handling:** Strict mode (`set -e`, `set -u`)
- **Permissions:** Handle with `sudo` where necessary; document privilege requirements

### Configuration
- **Format:** YAML for human readability
- **Paths:** Use environment variables and `/etc/hailo/` or `/opt/hailo/` conventions
- **Secrets:** Never hardcode; use `.env` files or systemd EnvironmentFile

## System Setup Prerequisites

Before deploying any service, the Hailo-10H kernel driver must be installed:
```bash
sudo apt install dkms hailo-h10-all
sudo reboot
hailortcli fw-control identify  # Verify installation
```

All AI HAT+ 2 specifics (device naming, PCIe settings) are documented in `reference_documentation/system_setup.md`.

## Key Considerations

- **Resource Constraints:** Raspberry Pi 5 has limited CPU/RAM (~5-6GB available); optimize for low overhead
- **Thermal Management:** Monitor and document thermal limits; consider passive cooling
- **Model Lifecycle:** Favor persistent model loading (startup latency is costly); unload gracefully only when necessary
- **Concurrent Services:** Hailo-10H supports multiple services running simultaneously; plan memory budgets accordingly
- **Systemd Integration:** Use Type=notify or Type=idle for proper process supervision
- **Logging:** All services log to journald; avoid direct file logging unless necessary
- **Python Package Management:** Pin exact versions in requirements.txt to avoid upstream breaking changes (e.g., piper-tts 1.4.0 bug)
- **Model Downloads:** Prefer Hugging Face over GitHub releases for more reliable artifact hosting and versioning

## Deployment Workflow

1. **Initialize:** Run system setup scripts to ensure Hailo driver is installed
2. **Install:** Service installer script configures systemd unit, creates users, manages permissions
3. **Configure:** YAML configuration file for service-specific settings
4. **Test:** Verify systemd status, API health checks, resource usage
5. **Debug:** Access logs via `journalctl -u service-name -f`

## Documentation Guidelines

Each service must include:
- **README.md** - Overview, installation, configuration
- **API_SPEC.md** - REST endpoints, request/response formats
- **TROUBLESHOOTING.md** - Common issues, verification steps
- **ARCHITECTURE.md** - Design decisions, resource model, limitations

---

**Last Updated:** January 2026  
**Reference:** See `reference_documentation/system_setup.md` for initial Hailo-10 setup
