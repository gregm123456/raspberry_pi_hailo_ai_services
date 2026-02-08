# Raspberry Pi Hailo AI Services

**Multiple AI services running concurrently on the Hailo-10H NPU through intelligent device management**

This project transforms the [Raspberry Pi AI HAT+ 2 (Hailo-10H)](https://www.raspberrypi.com/news/introducing-the-raspberry-pi-ai-hat-plus-2-generative-ai-on-raspberry-pi-5/) into a multi-service AI platform by solving the core challenge: **the NPU can only handle one inference context at a time**. Through a custom device manager and service architecture, up to 6 AI services can be loaded simultaneously as hot, available APIs.

## Demo Video

[![Hailo-10H Multiple AI Services Demo](https://img.youtube.com/vi/rwhzHg_7i9c/maxresdefault.jpg)](https://www.youtube.com/watch?v=rwhzHg_7i9c)

*Watch the demo: Testing multiple vision, language, and audio AI services running concurrently on a Raspberry Pi 5*

## Hardware Requirements

- **Raspberry Pi 5** (4GB+ RAM recommended)
- **Raspberry Pi AI HAT+ 2** with Hailo-10H NPU (13 TOPS)
- **64-bit Raspberry Pi OS** (Trixie - Debian 13)
- **Hailo driver and runtime** installed (`hailo-all` package)

## The Problem This Solves

The Hailo-10H NPU is powerful but exclusive—only one service can create an inference context (VDevice) at a time. Starting a second service fails with:

```
HAILO_OUT_OF_PHYSICAL_DEVICES(74): Failed to create vdevice.
there are not enough free devices. requested: 1, found: 0
```

Traditional workflows require stopping one service before starting another, making it impractical to run multiple AI capabilities simultaneously.

## Key Features

### 1. 🎯 Hailo Device Manager
**Centralized device access and request serialization**

The device manager holds the exclusive VDevice connection and queues inference requests from multiple services. Services become lightweight clients communicating via Unix socket, enabling concurrent operation without device conflicts.

**Features:**
- Exclusive VDevice ownership with request queueing
- Unix socket API (`/run/hailo/device.sock`)
- Model caching in Hailo VRAM (8GB dedicated)
- Graceful request serialization (~10-20ms IPC overhead)
- Hot-swappable service integration

**Architecture:**
```
┌─────────────────────────────────────────────┐
│         Hailo Device Manager                │
│  • Exclusive VDevice                        │
│  • Request Queue (serialization)            │
│  • Model Registry (VRAM caching)            │
│  • Unix Socket: /run/hailo/device.sock      │
└─────────────────────────────────────────────┘
         ▲              ▲              ▲
         │              │              │
    ┌────────┐     ┌────────┐    ┌────────┐
    │ Vision │     │  CLIP  │    │Whisper │
    │(Client)│     │(Client)│    │(Client)│
    └────────┘     └────────┘    └────────┘
```

📖 [Full Device Manager Documentation](device_manager/README.md)

### 2. 🚀 System Services with REST APIs

Manufacturer-provided Hailo applications repackaged as persistent systemd services with standardized REST APIs:

| Service | Description | Status | Port | API Standard |
|---------|-------------|--------|------|--------------|
| **hailo-clip** | Zero-shot image classification | ✅ Production | 5000 | OpenAI-inspired |
| **hailo-vision** | Vision-language model (Qwen2-VL-2B) | ✅ Production | 11435 | OpenAI Chat API |
| **hailo-whisper** | Speech-to-text (Whisper-Base) | ✅ Production | 11437 | OpenAI Whisper API |
| **hailo-ocr** | Text detection + recognition | ✅ Production | 11436 | Custom |
| **hailo-pose** | Human pose estimation (YOLOv8) | ✅ Production | 11440 | Custom |
| **hailo-depth** | Monocular depth estimation | ✅ Production | 11439 | Custom |
| **hailo-piper** | Text-to-speech (Piper TTS) | ✅ Production | 5003 | OpenAI TTS API |
| **hailo-ollama** | LLM inference (Qwen2.5-1.5B) | ⚠️ Production | 11434 | Ollama API |

**⚠️ Exception: hailo-ollama** uses a precompiled binary that doesn't support the device manager architecture. It requires exclusive device access and cannot run concurrently with other services.

Each service includes:
- Full API specification (`API_SPEC.md`)
- Architecture documentation (`ARCHITECTURE.md`)
- Installation scripts (`install.sh`)
- Systemd service units
- Integration tests

#### Draft/Experimental Services

The following services are in active development or awaiting additional work:

- **hailo-face** — Face detection and embedding comparison
- **hailo-scrfd** — Specialized face detection (SCRFD)
- **hailo-florence** — Vision understanding and captioning (installer complete; HEF files require Hailo-10H recompilation)

These services have installer scripts and partial implementations in [`system_services/`](system_services/) but their adaptations to the required structure for this project are incomplete.

📁 [Browse System Services](system_services/)

### 3. 🎨 Gradio Web Portal

**Unified Web UI for testing, monitoring, and managing all AI services**

A comprehensive web interface providing:
- **Service test tabs** — Full API coverage for all 8 services with file uploads
- **Device status monitor** — Real-time temperature, memory, and loaded models
- **Service control** — Start/stop/restart services via systemctl
- **Parameter tuning** — All optional parameters exposed (sliders, dropdowns, etc.)
- **Response visualization** — JSON results, audio playback, depth maps, pose keypoints

Access at `http://localhost:7860` after installation.

📖 [Web Portal Documentation](system_services/hailo-web-portal/PLAN_hailo-web-portal.md)

## Quick Start

### 1. Install Hailo Prerequisites

```bash
sudo apt update
sudo apt full-upgrade
sudo apt install dkms hailo-all
sudo reboot

# Verify installation
hailortcli fw-control identify
```

### 2. Clone This Repository

```bash
git clone --recursive https://github.com/gregm123456/raspberry_pi_hailo_ai_services.git
cd raspberry_pi_hailo_ai_services
```

### 3. Install Device Manager

```bash
cd device_manager
sudo ./install.sh
sudo systemctl status hailo-device-manager
```

### 4. Install Services

Example: Install vision and CLIP services:

```bash
cd system_services/hailo-vision
sudo ./install.sh

cd ../hailo-clip
sudo ./install.sh
```

Repeat for other services as needed.

### 5. Install Web Portal

```bash
cd system_services/hailo-web-portal
sudo ./install.sh

# Access portal
xdg-open http://localhost:7860
```

### 6. Test Concurrent Operation

```bash
# Test device manager with multiple services
cd device_manager
python3 test_concurrent_services.py

# Access Web Portal to test all services
xdg-open http://localhost:7860
```

## Architecture

**System Overview:**

```
┌────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 5 + Hailo-10H             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Hailo Device Manager (systemd)               │  │
│  │  • Exclusive VDevice (Hailo-10H @ /dev/hailo0)       │  │
│  │  • Model Cache (8GB VRAM)                            │  │
│  │  • Request Queue + Serialization                     │  │
│  │  • Unix Socket: /run/hailo/device.sock               │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ▲ ▲ ▲ ▲ ▲                           │
│                        │ │ │ │ │                           │
│  ┌─────────────────────┴─┴─┴─┴─┴────────────────────────┐  │
│  │          System Services (systemd + REST APIs)       │  │
│  │  • hailo-vision (11435)    • hailo-clip (5000)       │  │
│  │  • hailo-whisper (11437)   • hailo-ocr (11436)       │  │
│  │  • hailo-pose (11440)      • hailo-depth (11439)     │  │
│  │  • hailo-piper (5003)                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ▲ ▲ ▲ ▲ ▲                           │
│  ┌─────────────────────┴─┴─┴─┴─┴────────────────────────┐  │
│  │          Gradio Web Portal (7860)                    │  │
│  │  • Service Testing UI                                │  │
│  │  • Device Monitoring                                 │  │
│  │  • Service Control                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Design Philosophy:**

1. **Build on Standards** — Adopt existing protocols (Ollama API, OpenAI API patterns) rather than inventing new ones
2. **Modular Services** — Each service is self-contained with its own installation, configuration, and documentation
3. **Pragmatic Over Perfect** — Optimized for personal projects and art installations, not production enterprise systems
4. **Systemd Integration** — Persistent services with automatic restart, journald logging, and resource limits

## Git Submodules

This repository includes several official Hailo repositories as submodules:

| Submodule | Purpose | License |
|-----------|---------|---------|
| [**hailo-apps**](https://github.com/hailo-ai/hailo-apps) | Application infrastructure and examples | [MIT](https://github.com/hailo-ai/hailo-apps/blob/095deb51bd723793a2d380c56f55986a8fd81478/LICENSE) |
| [**hailo-rpi5-examples**](https://github.com/hailo-ai/hailo-rpi5-examples) | Raspberry Pi 5 specific examples | [MIT](https://github.com/hailo-ai/hailo-rpi5-examples/blob/f53c003197a502fcca4f60bfb8766166d4905171/LICENSE) |
| [**hailo_model_zoo**](https://github.com/hailo-ai/hailo_model_zoo) | Pre-trained models and compilation tools | [MIT](https://github.com/hailo-ai/hailo_model_zoo/blob/c83fc030e862de8daf05b783f503712d168ef620/LICENSE) |
| [**hailo_model_zoo_genai**](https://github.com/hailo-ai/hailo_model_zoo_genai) | Generative AI models | [MIT](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/8eb58a6ff6719fee9528c4e057b800438f2405cd/LICENSE) |
| [**hailort**](https://github.com/hailo-ai/hailort) | Runtime libraries and tools | [MIT + LGPL 2.1](https://github.com/hailo-ai/hailort/blob/41a720b9fedb56a4ee9ea39506afecf3f9ace2eb/README.md#licenses) |

**Note:** The submodules are included for reference and building custom services. Most users can install pre-built packages via `apt install hailo-all`.

## Community & Discussion

**Forum Posts:**
- [Hailo Community - 6 services via VDevice management](https://community.hailo.ai/t/hailo-10h-successfully-loading-6-services-as-hot-available-apis-via-vdevice-inference-context-management/18730)
- [Raspberry Pi Forums - Multiple AI services demo](https://forums.raspberrypi.com/viewtopic.php?t=396078&sid=329fd1b8e46e2d954ef72c256f32ea65)

## Related Projects

This tooling was created in the spirit of supporting interactive art installations like this previous project of mine:
- [**Coyote Interactive**](https://github.com/gregm123456/coyote_interactive) — Multi-modal AI art installation ([YouTube demo](https://www.youtube.com/watch?v=pncuq-U_tuU))

## Documentation

- [Device Manager Architecture](device_manager/ARCHITECTURE.md)
- [Device Manager API Specification](device_manager/API_SPEC.md)
- [System Setup Guide](reference_documentation/system_setup.md)

## Troubleshooting

### Device conflicts
```bash
# Check device manager status
sudo systemctl status hailo-device-manager

# View device status
curl http://127.0.0.1:5099/v1/device/status

# Restart device manager
sudo systemctl restart hailo-device-manager
```

### Service won't start
```bash
# Check logs
sudo journalctl -u hailo-SERVICE-NAME -n 50 --no-pager

# Verify device manager is running
systemctl is-active hailo-device-manager

# Check if another service is using the device
lsof /dev/hailo0
```

### Ollama conflicts
Ollama requires exclusive device access. Stop other services before starting:
```bash
sudo systemctl stop hailo-vision hailo-clip hailo-whisper
sudo systemctl start hailo-ollama
```

## Performance Notes

- **Inference Latency:** +10-20ms IPC overhead via device manager
- **Model Loading:** One-time cost on first inference; models stay cached in 8GB Hailo VRAM
- **Concurrent Requests:** Serialized by device manager; queue depth visible via status API
- **Thermal:** Monitor device temperature; passive cooling recommended for sustained workloads
- **Memory:** Services use minimal Pi RAM; models loaded into Hailo VRAM not system RAM

## Contributing

This is a personal project for art installations. Contributions are welcome but not actively solicited. If you use this code for your own projects, I'd love to hear about it!

**Areas for Contribution:**
- Additional service integrations
- Performance optimizations
- Documentation improvements
- Bug reports and fixes

## License

This project is licensed under the [MIT License](LICENSE).

### Submodule Licenses

The included git submodules have their own open-source licenses:

- **hailo-apps, hailo-rpi5-examples, hailo_model_zoo, hailo_model_zoo_genai** — MIT License
- **hailort** — MIT License (libhailort, pyhailort, hailortcli) and LGPL 2.1 (hailonet)

See the individual LICENSE files in each submodule directory for complete details.

## Acknowledgments

- **Hailo** for the incredible AI HAT+ 2 and comprehensive model zoo
- **Raspberry Pi Foundation** for the Raspberry Pi 5 platform
- The open-source community for tools like Gradio, FastAPI, and systemd

---

**Author:** Greg Merritt ([@gregm123456](https://github.com/gregm123456))  
**Project Start:** 2025  
**Last Updated:** February 2026
