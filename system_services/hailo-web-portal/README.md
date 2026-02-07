# Hailo Web Portal

Unified Gradio portal for testing and managing Hailo AI system services on Raspberry Pi 5.

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- Device manager service running: `sudo systemctl status hailo-device-manager.service`

## Installation

```bash
cd system_services/hailo-web-portal
sudo ./install.sh
sudo systemctl status hailo-web-portal.service
```

## Configuration

- Device status endpoint: `HAILO_DEVICE_STATUS_URL` (default: `http://127.0.0.1:5099/v1/device/status`)
- The portal binds to `127.0.0.1:7860` by default.

## Usage

Open the portal in a browser:

```
http://localhost:7860
```

Common commands:

```bash
sudo systemctl restart hailo-web-portal.service
sudo journalctl -u hailo-web-portal.service -f
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and fixes.

## Documentation

- [API_SPEC.md](API_SPEC.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
