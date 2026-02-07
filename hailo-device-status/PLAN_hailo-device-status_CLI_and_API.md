# Hailo Device Status Utility: CLI and API Plan

## Overview

Build a custom device status utility using HailoRT Python API to expose Hailo-10H NPU status information (architecture, firmware, network groups, loaded models, temperature) via CLI and optional API endpoint. This replaces the non-functional `hailortcli monitor` feature.

**Goals:**
- CLI utility: `hailo-device-status` command for quick status checks
- API endpoint: `/v1/device/status` in device_manager for programmatic access
- Expose: Device info, firmware version, loaded networks, temperature, utilization metrics

**Architecture:**
- Standalone CLI utility using HailoRT Python API directly
- HTTP endpoint in device_manager for global device status (cross-process network visibility)
- Follows project patterns: systemd service, isolated venv, YAML config

## Phase 1: Prototype (Standalone CLI Utility)

### Objectives
- Explore HailoRT Python API capabilities
- Create minimal CLI utility that queries device status
- Validate API access works with running inferences

### Implementation
1. **Create hailo-device-status directory structure:**
   ```
   hailo-device-status/
   ├── hailo_device_status.py  # Main CLI script
   ├── requirements.txt        # hailo_platform, click
   ├── README.md               # Usage documentation
   └── test_hailo_device_status.py  # Basic tests
   ```

2. **hailo_device_status.py implementation:**
   - Use `hailo_platform` to enumerate devices
   - Query device properties: architecture, firmware, temperature
   - For loaded networks: Use VDevice API to get network groups
   - CLI interface with `click` library
   - Output formats: human-readable, JSON

3. **Key API calls to explore:**
   ```python
   from hailo_platform import Device, VDevice

   # Device enumeration and basic info
   devices = Device.scan()
   device = devices[0]
   print(f"Device: {device.get_physical_device_id()}")
   print(f"Architecture: {device.get_architecture()}")
   print(f"Firmware: {device.get_fw_version()}")

   # Temperature (if available)
   temp = device.get_temperature()  # May not be implemented

   # For loaded networks - need VDevice access
   # This might require coordination with device_manager
   ```

### Testing
- Run with device_manager active (inferences running)
- Compare output with `hailortcli fw-control identify`
- Verify no interference with running services

### Timeline: ~2 hours
- 1h: API exploration and prototyping
- 1h: CLI interface and testing

### Phase 1 Completion Notes (February 2026)
**Status: ✅ COMPLETE & VALIDATED**

**Implementation Summary:**
- Created `hailo_device_status.py` (418 lines) with 4 CLI commands: `device`, `networks`, `status`, `health`
- Full HailoRT Python API integration: Device enumeration, board info, temperature sensors, network groups
- CLI interface using Click with human-readable and JSON output formats
- Comprehensive test suite: 16 unit tests, all passing (TestDeviceInfo, TestNetworksInfo, TestFormatting, TestCLICommands)
- Complete documentation: README.md, ARCHITECTURE.md, API_FIXES_SUMMARY.md

**Key Achievements:**
- Device info retrieval: Device ID, architecture, firmware version
- Temperature monitoring: ts0_temperature sensor via device.control.get_chip_temperature()
- Network tracking: Per-process visibility (VDevice and Device.loaded_network_groups APIs)
- Color-coded terminal output (green/yellow/red based on severity)
- Health check command with exit codes (0=accessible, 1=unavailable)
- JSON output for programmatic access

**Discovered API Constraints:**
- Device.scan() returns device ID strings, not objects
- VDevice initialization doesn't require VDeviceParams
- loaded_network_groups only shows networks loaded by THIS PROCESS (architectural limitation)
- Other processes' networks not visible; requires device_manager for cross-process visibility

**Hardware Validation:**
- Tested on Raspberry Pi 5 with Hailo-10H NPU
- Device ID: 0001:01:00.0, Architecture: HAILO10H, Firmware: 5.1.1 (release,app)
- Temperature monitoring functional (~53°C typical idle)
- No interference with concurrent inferences

**Example Output:**
```
$ python3 hailo_device_status.py device
Hailo Devices
Found: 1 device(s)

Device 0:
  Device ID:     0001:01:00.0
  Architecture:  HAILO10H
  Firmware:      5.1.1 (release,app)
  Temperature:   53.5°C

$ python3 hailo_device_status.py health
✓ Device accessible
$ echo $?
0
```

**Ready for:**
- Phase 2: REST API integration with device_manager (/v1/device/status endpoint)
- Phase 3: Systemd service packaging (optional)

## Phase 2: Integration with Device Manager (Optional Endpoint)

### Objectives
- Add `/v1/device/status` endpoint to device_manager
- Leverage existing VDevice ownership in device_manager for cross-process network visibility
- Provide programmatic access for monitoring tools
- **Primary Motivation:** Solve Phase 1 architectural limitation (per-process network visibility)

### Implementation
1. **Extend device_manager/hailo_device_manager.py:**
   - Add `get_device_status()` method using VDevice API
   - Return structured data: device info, networks, temperature
   - Handle cases where VDevice not initialized

2. **Add API endpoint in device_manager API:**
   - New route: `GET /v1/device/status`
   - JSON response with status data
   - Update API_SPEC.md documentation

3. **RPC consideration:**
   - If direct VDevice access not possible, add RPC method
   - Services can query via device_manager instead of direct API

### File Changes
- `device_manager/hailo_device_manager.py`: Add status method
- `device_manager/device_client.py`: Add status query method
- `device_manager/API_SPEC.md`: Document new endpoint

### Testing
- Test endpoint with curl: `curl http://localhost:5000/v1/device/status`
- Verify data matches CLI utility output
- Test with/without active inferences

### Timeline: ~1 hour
- 30m: Implement status method in device_manager
- 30m: Add API endpoint and test

### Phase 2 Readiness (Post-Phase 1)
**Status:** READY TO IMPLEMENT

Phase 1 completion has identified the exact requirement: Since each independent Device instance only sees networks loaded within its own process, the `/v1/device/status` endpoint must run within device_manager's process to leverage its VDevice ownership. This will provide the global network visibility that CLI cannot achieve.

**Implementation Approach:**
1. Extend device_manager to expose `get_device_status()` method on its VDevice
2. Hook into device_manager's Flask API to add `/v1/device/status` endpoint
3. CLI can optionally query this endpoint as alternative data source
4. Services can query device_manager instead of maintaining separate Device instances

### Phase 2 Completion Notes (February 2026)
**Status: ✅ COMPLETE (HTTP API)**

**Implementation Summary:**
- Added optional HTTP status server in `device_manager/hailo_device_manager.py`
   - ThreadingHTTPServer on configurable bind address (default `127.0.0.1:5099`)
   - `GET /v1/device/status` endpoint returning same payload as socket `device_status` action
   - Lifecycle management (start/stop with device manager)
- Updated CLI `hailo_device_status.py` to prefer HTTP endpoint when available
   - Falls back to direct HailoRT access if device manager HTTP endpoint unavailable
   - Enhanced network formatting to show global vs per-process scope
- Resolved port conflict: Changed default from 5000 to 5099 (avoided hailo-clip on 5000)
- Updated documentation: API_SPEC.md, README.md, port reconciliation plan

**Result:**
- Cross-process visibility achieved via device_manager HTTP API
- CLI shows "Count: 1 (global)" when using device_manager endpoint
- HTTP endpoint provides programmatic access for monitoring tools
- Backward compatible: CLI works with or without device_manager running

**HTTP Endpoint Details:**
- URL: `http://127.0.0.1:5099/v1/device/status`
- Method: GET
- Response: JSON payload identical to socket `device_status` action
- Configuration: `HAILO_DEVICE_HTTP_BIND` env var (default `127.0.0.1:5099`)
- Disable: Set `HAILO_DEVICE_HTTP_BIND=off`

**CLI Integration:**
- Prefers device_manager HTTP endpoint for full device status
- Falls back to direct HailoRT access (per-process network visibility)
- Environment: `HAILO_DEVICE_STATUS_URL` (default `http://127.0.0.1:5099`)
- Timeout: 0.5s (configurable via `HAILO_DEVICE_STATUS_TIMEOUT`)

**Validation:**
```bash
# HTTP endpoint working
curl http://localhost:5099/v1/device/status | jq
# Returns: device info + global networks (1 loaded model)

# CLI using HTTP endpoint
python3 hailo_device_status.py status
# Shows: "Count: 1 (global)" with network details
```

**Next Steps:** Phase 2 complete; optional Phase 3 (systemd service) if persistent monitoring needed.

## Phase 3: Production Service (Optional)

### Objectives
- Package as systemd service for persistent monitoring
- Add configuration options (polling interval, output formats)
- Integration with project deployment patterns

### Implementation
1. **Service structure:**
   ```
   hailo-device-status/
   ├── hailo-device-status.service  # systemd unit
   ├── install.sh                   # Installation script
   ├── config.yaml                  # Service configuration
   ├── API_SPEC.md                  # API documentation
   └── ARCHITECTURE.md              # Design notes
   ```

2. **Service features:**
   - Background monitoring with configurable interval
   - Log to journald
   - Health checks and status reporting
   - Follow venv isolation pattern

3. **Configuration:**
   - YAML config for output formats, endpoints
   - Environment variables for customization

### Deployment
- Follow device_manager install.sh pattern
- Create hailo-device-status user
- Manage permissions for device access

### Timeline: ~2 hours
- 1h: Service packaging and configuration
- 1h: Installation script and testing

## Technical Considerations

### API Access Patterns
- **Direct access:** CLI utility queries device directly (requires device not owned by device_manager)
- **Via device_manager HTTP:** API endpoint uses existing VDevice ownership for global visibility
- **RPC proxy:** Services query device_manager instead of direct API

### Data Sources
- **Device info:** `hailo_platform.Device` methods
- **Firmware:** `get_fw_version()`
- **Networks:** VDevice `get_network_groups()` or direct Device.loaded_network_groups
- **Temperature:** `device.control.get_chip_temperature()` returns TemperatureInfo
- **Utilization:** May require custom monitoring (not available in current HailoRT)

### Network Visibility Limitation (Phase 1 Finding)
**Critical Architectural Constraint:**
Each HailoRT Device instance only sees networks it has loaded within its own process context. Networks loaded by other processes (e.g., device_manager owning the VDevice, concurrent inference tests) are invisible to independent Device instances.

**Implication for Phase 2:**
To expose all loaded networks across processes, the API endpoint must run within device_manager's process context, leveraging its VDevice ownership. This cannot be solved in Phase 1 (standalone CLI) but is the primary motivation for Phase 2.

**Practical Example:**
- CLI runs `hailo_device_status` → Device instance → sees 0 networks
- Concurrently: `vision_test.sh` running → its Device instance → sees and loads networks
- Result: Different Device instances, different network visibility (both correct by HailoRT design)


### Error Handling
- Device not found: Graceful error messages
- API failures: Fallback to partial data
- Permission issues: Clear error reporting

### Security
- No sensitive data exposure
- Read-only access to device status
- Follow project permission patterns

## Success Criteria

### Phase 1
- [x] CLI utility runs without errors
- [x] Displays device architecture and firmware
- [x] Shows loaded networks (process-local only, architectural limitation)
- [x] JSON output format works
- [x] All 16 unit tests passing
- [x] Temperature sensor integration working
- [x] Health check with proper exit codes

### Phase 2
- [x] API endpoint returns valid JSON
- [x] Data matches CLI utility output
- [x] No performance impact on inferences
- [x] HTTP endpoint provides global network visibility
- [x] CLI prefers device_manager endpoint when available
- [x] Backward compatible fallback to direct access

### Phase 3
- [ ] Service installs and starts successfully
- [ ] Logs to journald properly
- [ ] Survives reboots

## Dependencies

- `hailo_platform` Python package (HailoRT Python API)
- `click` for CLI interface
- `pyyaml` for configuration
- `flask` for API (if integrated with device_manager)

## Risk Assessment

### Phase 1 Risks (Resolved ✅)
- **HailoRT Python API may not expose all desired metrics** → RESOLVED: Device.scan(), control.identify(), get_chip_temperature() all confirmed working
- **API access patterns unclear** → RESOLVED: VDevice vs Device behavior well understood; discovered per-process network visibility
- **Temperature/utilization data may not be available** → RESOLVED: Temperature working; utilization not available (expected)

### Remaining Risks/Limitations
- **Per-process network visibility (HailoRT architectural constraint)** → **MITIGATED:** Phase 2 HTTP endpoint provides global visibility when device_manager is running
- **Device ownership conflicts** → MITIGATION: Phase 2 runs within device_manager process to leverage existing VDevice
- **Backward compatibility with existing services** → LOW RISK: Phase 2 is additive endpoint

## Next Steps

1. **✅ Phase 1 COMPLETE:** CLI utility exploring HailoRT Python API and prototyping done
2. **✅ Phase 2 COMPLETE:** HTTP API endpoint in device_manager for cross-process network visibility
   - Implemented within device_manager's process context where VDevice ownership exists
   - CLI now uses HTTP endpoint for global device status when available
   - Falls back to direct HailoRT access for backward compatibility
3. **Optional Phase 3:** Package as standalone service if persistent monitoring needed
