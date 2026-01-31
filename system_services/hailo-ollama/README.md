# Hailo Ollama Service

Deploys the upstream `hailo-ollama` server as a systemd service on Raspberry Pi 5 with Hailo-10H, exposing an Ollama-compatible API on port 11434.

## Prerequisites

- Hailo-10H driver installed: `sudo apt install dkms hailo-h10-all`
- Verify device: `hailortcli fw-control identify`
- Python YAML support: `sudo apt install python3-yaml`

The installer will check for the `hailo-ollama` binary (from Developer Zone Debian package) and provide installation guidance if missing.

## Installation

```bash
cd system_services/hailo-ollama
sudo ./install.sh
```

Optional warmup:

```bash
sudo ./install.sh --warmup-pull qwen2:1.5b
sudo ./install.sh --warmup-chat qwen2:1.5b
```

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-ollama.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11434

library:
  host: dev-public.hailo.ai
  port: 443

main_poll_time_ms: 200
```

The installer renders upstream JSON to `/etc/xdg/hailo-ollama/hailo-ollama.json`.

After changes, re-run:

```bash
sudo ./install.sh
```

## Basic Usage

```bash
curl http://localhost:11434/api/version
curl http://localhost:11434/api/tags
```

Check service status:

```bash
sudo systemctl status hailo-ollama.service
sudo journalctl -u hailo-ollama.service -f
```

## Verification

```bash
sudo ./verify.sh
```

## Uninstall

```bash
sudo ./uninstall.sh
```

Optional cleanup:

```bash
sudo ./uninstall.sh --remove-user --purge-data
```

## Documentation

- API reference: [API_SPEC.md](API_SPEC.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
