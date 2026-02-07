# Hailo Device Status Utility

Quick CLI utility to query Hailo-10H NPU device status, firmware version, loaded networks, and temperature information.

## Prerequisites

- Hailo-10H driver installed: `sudo apt install hailo-h10-all`
- Verify installation: `hailortcli fw-control identify`
- Python 3.10+

## Installation

```bash
cd hailo-device-status
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Make the script executable:
```bash
chmod +x hailo_device_status.py
```

## Quick Usage

### Device Information
```bash
python3 hailo_device_status.py device
```

Output:
```
Hailo Devices
Found: 1 device(s)

Device 0:
  Device ID:     0000:04:00.0
  Architecture:  HAILO_ARCH_H10_A
  Firmware:      4.28.8
  Temperature:   45.3°C
```

### Show Loaded Networks
List networks currently loaded (requires device_manager running):
```bash
python3 hailo_device_status.py networks
```

### Complete Status
Show device info + loaded networks:
```bash
python3 hailo_device_status.py status
```

### Health Check
Quick exit-code based health check:
```bash
python3 hailo_device_status.py health
echo $?  # 0 = device ok, 1 = not accessible
```

## JSON Output

All commands support `--json` flag for programmatic access:

```bash
python3 hailo_device_status.py device --json
```

Output:
```json
{
  "status": "ok",
  "device_count": 1,
  "devices": [
    {
      "index": 0,
      "device_id": "0000:04:00.0",
      "architecture": "HAILO_ARCH_H10_A",
      "fw_version": "4.28.8",
      "temperature_celsius": 45.3
    }
  ]
}
```

## Command Reference

```
hailo_device_status.py device      # Device architecture, firmware, temperature
hailo_device_status.py networks    # Currently loaded inference networks
hailo_device_status.py status      # Full device status (device + networks)
hailo_device_status.py health      # Health check (exit code 0/1)
hailo_device_status.py --help      # Show all options
```

## Testing

Run the test suite:
```bash
python3 test_hailo_device_status.py
```

This validates:
- Device enumeration works
- API calls don't crash
- Output formatting (human-readable and JSON)
- Error handling when device unavailable

## Troubleshooting

### "No Hailo devices detected"
**Cause:** Hailo driver not installed or device not recognized

**Fix:**
1. Verify driver: `sudo apt install hailo-h10-all`
2. Reboot: `sudo reboot`
3. Check device: `hailortcli fw-control identify`

### Temperature shows as unavailable
**Expected:** Device temperature API may not be implemented in all firmware versions.

**Workaround:** Use system temperature: `vcgencmd measure_temp`

### Networks show as empty even with device_manager running
**Cause:** No inferences currently active

**Fix:** Start an inference, then query networks again

### "Device not accessible" (health check fails)
**Cause:** Device permissions issue or driver not loaded

**Fix:**
```bash
# Check device exists
ls -la /dev/hailo0

# Add user to hailo group
sudo usermod -aG hailo $USER
# Log out and back in
```

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Design decisions and API details
- [API Specification](API_SPEC.md) - REST API endpoints (Phase 2)
- HailoRT Python API docs: [https://www.raspberrypi.com/documentation/computers/ai.html](https://www.raspberrypi.com/documentation/computers/ai.html)
