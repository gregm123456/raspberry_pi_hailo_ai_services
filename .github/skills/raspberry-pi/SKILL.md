---
name: raspberry-pi
description: Raspberry Pi 5 and Hailo-10H NPU system management
---

# Raspberry Pi 5 & Hailo-10 System Management

This skill provides practical guidance for deploying Hailo-10H services on Raspberry Pi 5—aimed at personal projects, art installations, and experimentation. Pragmatism over perfection; if it works reliably on the Pi, it's good enough.

**Scope:** Initial system setup, device access, thermal management, systemd service patterns, debugging.

## Hardware Overview

**Raspberry Pi 5:**
- 4-core ARM Cortex-A76 @ 2.4 GHz
- 8 GB LPDDR5 RAM (standard deployment config)
- PCIe 5.0 x1 slot (AI HAT+ 2 plugs here)
- 27W power budget (cooling via passive heatsink + active fan)
- Thermal throttle at 80°C; shutdown at ~85°C

**AI HAT+ 2 with Hailo-10H:**
- Hailo-10H NPU (Specs: TBD - reference Hailo product sheets)
- M.2 B+M Key form factor
- Requires `hailo-h10-all` package (NOT `hailo-all` for legacy boards)
- Single process can access at a time; managed via `/dev/hailo0` device file
- Kernel driver: `0000:01:00.0` PCIe address

## Initial System Setup

### Prerequisites
Before any AI service deployment:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo rpi-eeprom-update -a
sudo reboot
```

### Install Hailo Driver & Firmware

```bash
sudo apt install dkms hailo-h10-all
sudo reboot
```

### Verify Installation

```bash
# Check device detection
hailortcli fw-control identify

# Check kernel logs
dmesg | grep -i hailo | tail -20
```

Expected output shows: `Firmware was loaded successfully` and device registered as `/dev/hailo0`.

## Key Constraints & Considerations

### Concurrent Service Support
- **Hailo-10H supports multiple services running simultaneously** on the same device
- Each service can load its own model and run inference concurrently
- Memory is the primary constraint (~5-6GB available on Pi 5 with 8GB RAM)
- Plan memory budgets: leave headroom for OS + all active models

### Thermal Limits
- **Passive cooling:** typical 55-65°C under moderate load
- **Active fan:** cools to 45-55°C; enables sustained inference
- **Throttle threshold:** 80°C (CPU performance reduced)
- **Shutdown threshold:** ~85°C (emergency power-off)
- Monitor with: `vcgencmd measure_temp` or `/sys/class/thermal/thermal_zone0/temp`

### Memory & Storage
- **RAM budget:** 1-2 GB reserved for OS; ~5-6 GB available for AI services
- **Multiple concurrent services:** Budget memory across all active services (e.g., 2GB for Ollama + 1GB for Whisper + 1GB for vision)
- **Storage:** microSD card (typical 64-128 GB; prefer U3 rated)
- **Model caching:** Services cache models locally; startup latency is 10-30s per model
- **Preference:** Keep models loaded; avoid frequent unload/reload cycles

### CPU Considerations
- Pi 5 is single-socket ARM; all 4 cores are identical
- Hailo-10 offloads AI inference; CPU used for preprocessing, postprocessing
- Avoid CPU saturation (keep CPU usage <80% if possible) for responsive system

## systemd Service Best Practices

### Minimal Service Unit

```ini
[Unit]
Description=Hailo Ollama AI Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hailo
Group=hailo
WorkingDirectory=/opt/hailo/ollama
ExecStart=/usr/local/bin/hailo-ollama-service
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Resource limits for Raspberry Pi
MemoryLimit=2G
CPUQuota=75%

[Install]
WantedBy=multi-user.target
```

### Permission & User Setup

```bash
# Create dedicated user with no shell, no home
sudo useradd -r -s /usr/sbin/nologin -d /opt/hailo hailo

# Add to groups for device access
sudo usermod -aG hailo,plugdev,dialout hailo

# Hailo device group (usually created by hailo-h10-all package)
# If missing: sudo groupadd hailo && sudo chgrp hailo /dev/hailo0 && sudo chmod g+rw /dev/hailo0
```

### Python Service Deployment Strategy

**Default approach:** Per-service virtual environment in `/opt`

Python-based Hailo services (e.g., hailo-clip, hailo-vision, hailo-whisper) use isolated virtual environments to:
- Avoid dependency conflicts with system Python and other services
- Pin specific package versions for reproducibility
- Prevent system package manager interference
- Support services with conflicting Python dependencies

**Standard pattern:**
```bash
# Installer creates dedicated venv per service
python3 -m venv /opt/hailo-service-name/venv
/opt/hailo-service-name/venv/bin/pip install -r requirements.txt

# systemd unit references venv Python
ExecStart=/opt/hailo-service-name/venv/bin/python3 /opt/hailo-service-name/service.py
```

**Why /opt?**
- Standard FHS location for add-on software packages
- Isolated from OS updates and apt package management
- Clear separation from system Python in `/usr`
- Easy to back up, version, or remove entire service

**Alternative: Packaged binaries (PyInstaller, Nuitka, PEX)**

Use when installation simplicity outweighs build complexity:
- Single binary deployment (no venv needed)
- Suitable for shrink-wrapped installations
- Tradeoffs: larger binary size, more complex build process, harder debugging
- Consider for services where dependency management is particularly complex

**Not recommended: System Python with pip**

Avoiding system Python prevents:
- Conflicts with OS-managed packages (apt vs. pip)
- Breaking system tools that depend on specific Python packages
- Unexpected behavior after OS upgrades

**Service-specific considerations:**
- hailo-ollama: Not Python-based; wraps Ollama binary (no venv needed)
- hailo-clip, hailo-vision: Require HailoRT Python bindings, heavy CV dependencies (use /opt venv)
- Lightweight services: Can share a common venv if dependencies align (not recommended; isolate by default)

### Device Access in Services

```bash
# In installer script, ensure proper device permissions:
if [ -e /dev/hailo0 ]; then
    sudo chgrp hailo /dev/hailo0
    sudo chmod g+rw /dev/hailo0
else
    echo "ERROR: /dev/hailo0 not found. Hailo driver not installed."
    exit 1
fi

# Multiple services can share /dev/hailo0 access
# Each service user should be in the 'hailo' group:
sudo usermod -aG hailo hailo-ollama-user
sudo usermod -aG hailo hailo-whisper-user
# etc.
```

## Networking & API Services

### Port Selection
- **Ollama default:** 11434 (may conflict with other services)
- **Configurable range:** 1024-65535; avoid well-known ephemeral ports (49152+)
- **Firewall:** By default, only accessible on `127.0.0.1:PORT`; use systemd socket activation or reverse proxy for external access

### Logging via journald

```bash
# View service logs
sudo journalctl -u hailo-ollama.service -f

# Filter by priority
sudo journalctl -u hailo-ollama.service -p err..alert

# Export to file for analysis
sudo journalctl -u hailo-ollama.service -o json > service_logs.json
```

## Debugging & Troubleshooting

### Device Not Found

```bash
# Verify driver loaded
lsmod | grep hailo

# Check PCIe device
lspci | grep -i hailo

# If missing, reinstall:
sudo apt install --reinstall hailo-h10-all
sudo reboot
```

### Permission Denied on `/dev/hailo0`

```bash
# Check ownership and permissions
ls -l /dev/hailo0

# Ensure service user is in hailo group
id hailo-service-user

# If not, add with: sudo usermod -aG hailo hailo-service-user
# Then restart service: sudo systemctl restart service-name
```

### High Memory Usage with Multiple Services

```bash
# Check total memory consumption
free -h

# Identify which service is using most memory
ps aux --sort=-%mem | grep hailo

# Reduce memory per service:
# - Use smaller models (e.g., orca-mini instead of llama2)
# - Unload models via /api/unload when not in use
# - Reduce number of concurrent services
```

### Thermal Throttling

```bash
# Check current temperature
vcgencmd measure_temp

# Monitor over time
watch -n 1 vcgencmd measure_temp

# Check throttle history
vcgencmd get_throttled  # Returns hex bitmask; decode at https://www.raspberrypi.org/forums/
```

### systemd Service Boot Issues

```bash
# Check unit status
sudo systemctl status hailo-ollama.service

# View error logs
sudo journalctl -u hailo-ollama.service -n 50

# Test service startup manually
sudo systemctl start hailo-ollama.service

# Validate unit file syntax
sudo systemd-analyze verify hailo-ollama.service
```

## Performance Tuning

### CPU Governor (if needed)
```bash
# Check current governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Set to performance (higher power, lower latency)
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### Memory Tuning
```bash
# Disable swap if performance-critical
sudo dphys-swapfile disable

# Check available memory
free -h
```

---

**Reference Files:**
- `reference_documentation/system_setup.md` - Full setup walkthrough
- Hailo documentation: https://www.raspberrypi.com/documentation/computers/ai.html
