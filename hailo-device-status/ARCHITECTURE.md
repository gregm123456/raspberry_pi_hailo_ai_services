# Hailo Device Status Utility - Architecture

## Purpose

Provide a lightweight CLI utility to query Hailo-10H NPU device status including firmware version, device architecture, loaded networks, and temperature. This replaces the non-functional `hailortcli monitor` feature with a pragmatic alternative using the HailoRT Python API directly.

## Design Principles

1. **Standalone utility**: Runs independently without requiring device_manager
2. **Direct API access**: Uses HailoRT Python bindings (hailo_platform) for device queries
3. **Graceful degradation**: Returns partial data if some metrics unavailable (e.g., temperature, networks)
4. **Simple integration**: No external daemon or service required for Phase 1
5. **Pragmatic output**: Human-readable by default, JSON for programmatic access

## Component Architecture

```
┌─── hailo_device_status.py ────────────────────┐
│                                                │
│  Command Line Interface (Click)                │
│  ├── device     - Device info (ID, arch, FW)  │
│  ├── networks   - Loaded inference networks   │
│  ├── status     - Complete status (all above) │
│  └── health     - Health check (exit code)    │
│                                                │
│  Output Formatters                             │
│  ├── format_device_output()    (human/JSON)   │
│  └── format_networks_output()  (human/JSON)   │
│                                                │
│  HailoRT API Wrappers                          │
│  ├── get_device_info()    (Device.scan())     │
│  └── get_loaded_networks() (VDevice API)      │
│                                                │
└────────────────────────────────────────────────┘
        │                          │
        └─→ /dev/hailo0         ├─→ device_manager
           (direct access)         (if running)
```

## Data Flow

### Command: `device`
```
User input
    ↓
Click CLI handler
    ↓
get_device_info()
    ↓
Device.scan() → HailoRT API → /dev/hailo0
    ↓
        ├─ get_physical_device_id()
        ├─ get_architecture()
        ├─ get_fw_version()
        └─ get_temperature() [optional]
    ↓
format_device_output() → Terminal or JSON
```

### Command: `networks`
```
User input
    ↓
Click CLI handler
    ↓
get_loaded_networks()
    ↓
Try VDevice() → device_manager RPC
    ↓
    ├─ Success: Parse network groups
    └─ Fail: Return empty networks + status
    ↓
format_networks_output() → Terminal or JSON
```

## API Access Patterns

### Phase 1 (Current): Direct Device Access
- Uses `hailo_platform.Device.scan()` for device enumeration
- Direct `/dev/hailo0` access (no device_manager dependency)
- VDevice access for networks (optional if device_manager running)
- **Pros:** No external dependencies, simple CLI
- **Cons:** Cannot query device owned by device_manager; networks only show if device_manager export them

### Phase 2 (Optional): Device Manager Integration
- Add `/v1/device/status` API endpoint in device_manager
- Services query via HTTP instead of direct HailoRT API
- Leverages device_manager's VDevice ownership
- **Pros:** Single source of truth; works with exclusive device access
- **Cons:** Requires device_manager running; adds HTTP overhead

## Output Formats

### Human-Readable (default)
```
Hailo Devices
Found: 1 device(s)

Device 0:
  Device ID:     0000:04:00.0
  Architecture:  HAILO_ARCH_H10_A
  Firmware:      4.28.8
  Temperature:   45.3°C

Loaded Networks
Count: 1
Source: VDevice (device_manager active)

yolo_detection
  Inputs:  1
  Outputs: 2
```

Color-coded output:
- **Green**: Normal (T < 65°C)
- **Yellow**: Warning (T 65-80°C, unavailable metrics)
- **Red**: Critical (T > 80°C, errors)

### JSON Output
All commands support `--json` flag for programmatic integration:
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

## Error Handling & Graceful Degradation

### Device Not Found
```
Status: error
Message: No Hailo devices detected
Exit code: 1
```

### Temperature Unavailable
```json
{
  "temperature_celsius": null,
  "temperature_error": "Not implemented"
}
```
Service continues with available metrics (device ID, firmware, architecture).

### VDevice Unavailable (device_manager not running)
```json
{
  "status": "unavailable",
  "network_count": 0,
  "networks": [],
  "note": "Device manager may not be running..."
}
```
Networks commands gracefully report unavailability without crashing.

## Constraints & Limitations

### Hardware Constraints
- **Single device access**: Only one process can access `/dev/hailo0` at a time
- **Read-only access**: Device status is read-only; no control/configuration
- **Temperature API**: May not be implemented in all firmware versions
- **Network visibility**: Only shows networks if you own VDevice or device_manager exports them

### Software Design
- **No daemon**: Phase 1 is CLI only (not a background service)
- **No API server**: Phase 1 has no HTTP API (Phase 2 adds `/v1/device/status`)
- **Sequential queries**: Commands run sequentially (not concurrent)
- **No caching**: Each invocation queries device fresh (ensures current data)

## Dependencies

### Required Packages
- **click** (8.1.7): CLI argument parsing and formatting
- **hailo_platform** (5.5.1): HailoRT Python bindings for device API

### System Requirements
- Hailo-10 driver installed: `hailo-h10-all`
- /dev/hailo0 accessible (permissions or group membership)
- Python 3.10+

## Testing Strategy

### Unit Tests (`test_hailo_device_status.py`)
- Mock HailoRT API calls
- Test success paths (device found, networks available)
- Test error paths (device not found, API failures)
- Test output formatting (JSON and human-readable)
- Test CLI command execution

### Integration Tests (manual)
- Run with actual Hailo device
- Verify device info matches `hailortcli fw-control identify`
- Run with device_manager active/inactive
- Compare network output with `device_manager` state

### Future Monitoring
- Phase 3 may add periodic polling (`hailo-device-status.service`)
- Systemd timer for regular status checks
- Logging to journald for historical analysis

## Known Issues & Workarounds

### Temperature Not Available
**Symptom:** `temperature_celsius: null` in output

**Cause:** Device API not implemented in firmware, or hardware sensor not supported

**Workaround:** Use system temperature instead:
```bash
vcgencmd measure_temp
```

### VDevice Access Blocked
**Symptom:** Networks always show as unavailable

**Cause:** device_manager owns exclusive device access

**Workaround:** Wait for Phase 2 API integration, or check device_manager logs

## Future Enhancements

### Phase 2: API Endpoint
- Add `/v1/device/status` endpoint to device_manager
- Return JSON status without CLI
- Enable monitoring tools to query status programmatically
- ~1 hour implementation

### Phase 3: System Service
- Package as `hailo-device-status.service`
- Periodic polling with configurable interval
- Export metrics to journald
- Prometheus metrics endpoint (optional)
- ~2 hours implementation

### Potential Additions
- Utilization metrics (if HailoRT API exposes them)
- Power consumption monitoring (if available)
- Model cache statistics
- Inference history/performance data
- Webhook notifications on thermal throttle

## Reference

- [HailoRT Python API Documentation](https://www.raspberrypi.com/documentation/computers/ai.html)
- [Device Manager Architecture](../../device_manager/ARCHITECTURE.md)
- [Project Documentation Standards](.github/skills/documentation/SKILL.md)
