# Raspberry Pi Hailo AI System Services

Modular, persistent system services for leveraging the Hailo-10H NPU acceleration on a Raspberry Pi 5. This project provides a collection of managed, standardized AI service APIs—think of them as the "system glue" for building AI applications that run reliably alongside other Pi workloads.

## What This Is

**Purpose:** Wrap Hailo-accelerated AI capabilities (LLMs, object detection, pose estimation, speech recognition, and more) as individual systemd services with standardized REST APIs.

**Philosophy:** Build atop existing standards and proven protocols rather than reinventing the wheel. Services adopt the conventions of their domains (Ollama-compatible REST for LLMs, Whisper API patterns for speech, COCO formats for vision). These are pragmatic, personal projects and art installations—functionality and ease of deployment matter more than theoretical perfection.

**Use Cases:**
- Run multiple AI models concurrently on a Pi, each managed as an independent service
- Build applications that call standardized AI endpoints
- Deploy AI capabilities that persist across reboots and integrate cleanly with systemd
- Experiment with Hailo-10H acceleration without writing kernel-level code

## Target Environment

- **Hardware:** Raspberry Pi 5 with AI HAT+ 2 (containing the Hailo-10H NPU)
- **OS:** 64-bit Raspberry Pi OS (Trixie or later)
- **Prerequisites:** Hailo-10H kernel driver and runtime (`dkms`, `hailo-h10-all`)
- **Management:** systemd service units for lifecycle control and logging via journald

## Services (In Development)

This project establishes standardized patterns for wrapping Hailo-accelerated AI capabilities as systemd services. Services planned include:

- **hailo-ollama** — LLM inference service (Ollama-compatible REST API) *[starting point]*
- **Object Detection** — YOLO/SSD bounding box detection
- **Pose Estimation** — YOLOv8 keypoint detection
- **Speech-to-Text** — Whisper-accelerated transcription
- **Text-to-Speech** — Piper TTS synthesis
- **OCR** — PaddleOCR text detection and recognition
- **Depth Estimation** — Monocular and stereo depth mapping
- **Face Recognition** — Detection and face embedding comparison

Each service will follow the same deployment patterns, offer idiomatic APIs for its domain, and integrate with systemd for reliable operation.

## Getting Started

### System Setup

Before services are ready, ensure your Raspberry Pi 5 has the Hailo driver installed:

```bash
sudo apt install dkms hailo-h10-all
sudo reboot
hailortcli fw-control identify  # Verify installation
```

See [reference_documentation/system_setup.md](reference_documentation/system_setup.md) for detailed setup and troubleshooting.

### Service Deployment (Coming Soon)

Each service directory will include an installer script for easy deployment:

```bash
cd system_services/hailo-ollama
sudo ./install.sh
```

Once deployed, services can be managed via systemd:

```bash
sudo systemctl start hailo-ollama
sudo systemctl status hailo-ollama
journalctl -u hailo-ollama -f
```

## Project Structure

```
system_services/
├── hailo-ollama/          # LLM service (Ollama-compatible)
│   ├── install.sh         # Deployment script
│   ├── service.py         # Service implementation
│   ├── hailo-ollama.service  # systemd unit
│   ├── config.yaml        # Configuration template
│   ├── README.md
│   ├── API_SPEC.md
│   ├── ARCHITECTURE.md
│   └── TROUBLESHOOTING.md
├── <future-service>/
└── ...

reference_documentation/
├── system_setup.md        # Hailo-10 initial setup
└── ...
```

## Coding Standards

- **Python:** 3.10+, PEP 8, type hints where they add clarity
- **Bash:** shellcheck-compliant, idempotent, strict error handling
- **Configuration:** YAML for readability
- **Logging:** Python `logging` module with systemd/journald integration
- **Philosophy:** Pragmatism over over-engineering; favor existing, proven libraries

## Key Considerations

- **Resource Constraints:** Raspberry Pi 5 has ~5–6 GB usable RAM; monitor memory usage during concurrent service operation
- **Thermal Management:** Hailo-10H and Pi CPU can heat up under load; consider passive cooling and monitor `vcgencmd measure_temp`
- **Model Persistence:** Keep models loaded during service lifetime to avoid startup latency
- **Concurrent Services:** The Hailo-10H supports multiple services; plan memory budgets accordingly
- **Systemd Integration:** Services use Type=notify or Type=idle for proper supervision

## Documentation

Each service includes:
- **README.md** — Overview, installation, configuration
- **API_SPEC.md** — REST endpoints, request/response formats
- **ARCHITECTURE.md** — Design decisions, resource model, limitations
- **TROUBLESHOOTING.md** — Common issues and verification steps

## Contributing

This project welcomes contributions, improvements, and refinements. If you extend services, add new capabilities, or improve documentation, please feel free to contribute.

## License

See individual service and submodule LICENSE files for details.

---

**Last Updated:** January 2026  
**Hailo-10H:** Requires kernel driver from Hailo Technologies  
**Reference:** [System Setup Guide](reference_documentation/system_setup.md)
