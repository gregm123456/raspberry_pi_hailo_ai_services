# Plan: Dashboard-style Device Status Redesign

## Overview

Replace the raw JSON display of device status with a user-friendly dashboard that presents key operational information in an at-a-glance format. The current `gr.JSON()` component is suitable for technical debugging but doesn't serve well as an information dashboard for monitoring Hailo device health and loaded networks.

## Goals

- **Operational Monitoring:** Provide quick visual indicators for device health, temperature, and loaded networks
- **Improved Usability:** Replace raw JSON with labeled, formatted displays that are easy to scan
- **Maintain Functionality:** Keep existing auto-refresh (3-second polling) and manual refresh capabilities
- **Resource Efficiency:** Ensure the redesign stays within the <200MB memory budget
- **Extensibility:** Design components that can be easily enhanced with additional metrics

## Current State Analysis

### Current Implementation
- Device status displayed using `gr.JSON(label="Device Status", value=monitor.get_status())`
- Auto-refresh every 3 seconds via `gr.Timer(3.0).tick()`
- Manual refresh button available
- Raw JSON structure shows all fields without formatting or prioritization

### Data Structure
The device status JSON contains:
```json
{
  "status": "ok",
  "device": {
    "device_id": "0001:01:00.0",
    "architecture": "HAILO10H",
    "fw_version": "5.1.1 (release,app)",
    "temperature_celsius": 51.3
  },
  "networks": {
    "status": "ok",
    "source": "device_manager",
    "network_count": 5,
    "networks": [
      {
        "name": "Whisper-Base.hef",
        "model_type": "whisper",
        "model_path": "/var/lib/hailo-whisper/resources/models/hailo10h/Whisper-Base.hef",
        "loaded_at": 1770479387.671931,
        "last_used": 1770479387.671931
      }
    ]
  },
  "uptime_seconds": 578.0739915370941,
  "queue_depth": 0
}
```

### Key Issues
- Raw JSON is hard to scan for operational status
- Timestamps are Unix epoch (not human-readable)
- No visual indicators for temperature thresholds
- Network information buried in nested structure
- No prioritization of critical vs. detailed information

## Proposed Solution

### Dashboard Layout
Replace single `gr.JSON()` with structured components:

1. **Device Header Row:** Single-line summary of device identity and uptime
2. **Temperature Gauge:** Color-coded visual indicator with threshold-based coloring
3. **Networks Table:** Formatted table showing loaded models with human-readable timestamps
4. **Queue Depth Indicator:** Simple numeric display of current request queue

### Component Specifications

#### Device Header
- **Component:** `gr.Textbox()` (read-only)
- **Content:** Concatenated string: "Hailo-10H (0001:01:00.0) | FW: 5.1.1 | Uptime: 9m 38s"
- **Purpose:** Quick device identification and operational status

#### Temperature Gauge
- **Component:** `gr.HTML()` with inline SVG (preferred) or `gr.HighChart()` if dependencies allow
- **Features:** Radial gauge with color-coded zones
- **Thresholds:** 
  - Green: <50°C (optimal)
  - Yellow: 50-65°C (warm)
  - Orange: 65-80°C (hot)
  - Red: >80°C (critical)
- **Display:** Current temperature prominently, with color background

#### Networks Table
- **Component:** `gr.Dataframe()`
- **Columns:** Model Name, Type, Loaded At, Last Used
- **Features:** Human-readable timestamps ("2 hours ago", "just now")
- **Purpose:** Overview of loaded AI models and their activity

#### Queue Depth
- **Component:** `gr.Label()` or `gr.Number()`
- **Display:** "Queue: 0" or "Queue: 3 pending"
- **Purpose:** Indicate current request backlog

### Data Transformation Layer

Create utility functions for data formatting:

#### Device Header Formatter
```python
def format_device_header(device_data: dict, uptime_seconds: float) -> str:
    """Format device info into readable header line."""
    arch = device_data.get('architecture', 'Unknown')
    device_id = device_data.get('device_id', 'Unknown')
    fw = device_data.get('fw_version', 'Unknown')
    uptime_str = format_uptime(uptime_seconds)
    return f"{arch} ({device_id}) | FW: {fw} | Uptime: {uptime_str}"
```

#### Temperature Color Logic
```python
def get_temperature_color(temp_celsius: float) -> str:
    """Return CSS color class based on temperature thresholds."""
    if temp_celsius < 50:
        return "green"
    elif temp_celsius < 65:
        return "yellow"
    elif temp_celsius < 80:
        return "orange"
    else:
        return "red"
```

#### Networks Table Formatter
```python
def format_networks_table(networks_data: dict) -> list[list[str]]:
    """Convert networks array to DataFrame-compatible format."""
    networks = networks_data.get('networks', [])
    table_data = []
    for net in networks:
        loaded_at = format_relative_time(net.get('loaded_at', 0))
        last_used = format_relative_time(net.get('last_used', 0))
        table_data.append([
            net.get('name', 'Unknown'),
            net.get('model_type', 'Unknown'),
            loaded_at,
            last_used
        ])
    return table_data
```

#### Time Formatting Utilities
```python
def format_uptime(seconds: float) -> str:
    """Convert seconds to human-readable uptime (e.g., '1h 23m')."""
    # Implementation for hours/minutes/seconds

def format_relative_time(epoch: float) -> str:
    """Convert epoch timestamp to relative time (e.g., '2 hours ago')."""
    # Implementation using datetime calculations
```

## Implementation Steps

### Phase 1: Data Transformation Module
1. Create `status_formatters.py` with utility functions
2. Implement time formatting functions
3. Add temperature threshold logic
4. Test formatters with sample data

### Phase 2: UI Component Redesign
1. Modify `build_gradio_interface()` in `app.py`
2. Replace `gr.JSON()` with structured layout using `gr.Row()` and `gr.Column()`
3. Add individual components for each dashboard section
4. Update the `update_status()` function to use formatters

### Phase 3: Integration and Testing
1. Wire up auto-refresh and manual refresh to new components
2. Test data flow from monitor → formatters → UI components
3. Verify temperature color changes with mock data
4. Test timestamp formatting accuracy

### Phase 4: Polish and Optimization
1. Adjust styling for visual consistency
2. Optimize memory usage (ensure <200MB)
3. Add error handling for malformed data
4. Document new components in README

## Technical Details

### Dependencies
- Existing: `gradio`, `fastapi`, `uvicorn`
- Potential additions: `humanize` for time formatting (check memory impact)

### Memory Considerations
- SVG gauge should be lightweight (<10KB)
- DataFrame component is efficient for tabular data
- Avoid heavy charting libraries if possible

### Async Patterns
- Maintain existing `asyncio` polling in `DeviceStatusMonitor`
- Ensure formatters are synchronous (no async I/O)
- Keep FastAPI endpoints non-blocking

### Error Handling
- Graceful degradation if device status unavailable
- Default values for missing fields
- Clear error indicators in dashboard

## Testing Strategy

### Unit Tests
- Test each formatter function with edge cases
- Verify temperature color logic
- Test time formatting accuracy

### Integration Tests
- End-to-end data flow: monitor → formatters → UI
- Auto-refresh functionality
- Manual refresh button

### User Acceptance
- Visual inspection of dashboard layout
- Temperature gauge responsiveness
- Network table readability
- Performance under load

## Risks and Mitigations

### Risk: Memory Budget Exceedance
- **Mitigation:** Use lightweight SVG for gauge; avoid heavy JS libraries
- **Fallback:** Simplify gauge to colored text box if needed

### Risk: Breaking Existing Functionality
- **Mitigation:** Keep existing API endpoints unchanged; only modify UI
- **Testing:** Comprehensive testing of refresh mechanisms

### Risk: Temperature Thresholds Incorrect
- **Mitigation:** Research Hailo-10H thermal specs; make thresholds configurable
- **Fallback:** Conservative thresholds with clear documentation

### Risk: Time Formatting Complexity
- **Mitigation:** Start with simple relative time; add ISO format option
- **Testing:** Verify accuracy across different time ranges

## Timeline and Resources

### Estimated Timeline
- Phase 1 (Formatters): 2-3 hours
- Phase 2 (UI Redesign): 4-6 hours
- Phase 3 (Integration): 2-3 hours
- Phase 4 (Polish): 1-2 hours
- **Total:** 1-2 days

### Resources Required
- Access to running Hailo device for testing
- Sample device status data for development
- Browser testing environment

### Success Criteria
- Dashboard loads without errors
- All components update within 3 seconds of data change
- Temperature gauge shows appropriate colors
- Networks table displays human-readable timestamps
- Memory usage remains <200MB
- No breaking changes to existing API

## Future Enhancements

- Configurable temperature thresholds
- Historical temperature charting
- Network usage statistics
- Alert notifications for critical temperatures
- Export functionality for debugging</content>
<parameter name="filePath">/home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-web-portal/PLAN_status_dashboard.md
