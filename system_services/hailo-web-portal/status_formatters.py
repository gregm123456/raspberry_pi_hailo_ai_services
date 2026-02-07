"""Status formatters for dashboard display.

Converts raw device status data into formatted, human-readable components
for the Hailo Web Portal dashboard.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List


# Temperature thresholds for Hailo-10H on Raspberry Pi 5
# Based on: safe operating range is typically 0-85°C
TEMP_THRESHOLDS = {
    "good": (0, 50),      # Optimal operating range
    "warm": (50, 65),     # Elevated but acceptable
    "hot": (65, 80),      # High, monitor carefully
    "critical": (80, 100),  # Dangerous, consider throttling
}

COLOR_MAP = {
    "good": "#4CAF50",       # Green
    "warm": "#FFC107",       # Yellow
    "hot": "#FF9800",        # Orange
    "critical": "#F44336",   # Red
}


def format_uptime(seconds: float) -> str:
    """Convert seconds to human-readable uptime format.
    
    Args:
        seconds: Uptime in seconds
        
    Returns:
        Formatted string like "1h 23m 45s" or "2m 30s"
    """
    if seconds < 0:
        return "unknown"
    
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    remaining = total_seconds % 3600
    minutes = remaining // 60
    secs = remaining % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def format_relative_time(epoch: float) -> str:
    """Convert epoch timestamp to relative time format.
    
    Args:
        epoch: Unix timestamp (seconds since epoch)
        
    Returns:
        Formatted string like "2 hours ago" or "just now"
    """
    if epoch <= 0:
        return "unknown"
    
    current_time = time.time()
    delta = current_time - epoch
    
    if delta < 0:
        return "in the future"
    
    if delta < 60:
        return "just now"
    
    minutes = int(delta // 60)
    if minutes < 60:
        return f"{minutes}m ago" if minutes != 1 else "1m ago"
    
    hours = int(delta // 3600)
    if hours < 24:
        return f"{hours}h ago" if hours != 1 else "1h ago"
    
    days = int(delta // 86400)
    if days < 7:
        return f"{days}d ago" if days != 1 else "1d ago"
    
    weeks = int(delta // 604800)
    return f"{weeks}w ago" if weeks != 1 else "1w ago"


def get_temperature_color(temp_celsius: float) -> str:
    """Get color code for temperature value based on thresholds.
    
    Args:
        temp_celsius: Temperature in Celsius
        
    Returns:
        Color name (good, warm, hot, critical) or hex color code
    """
    if temp_celsius < TEMP_THRESHOLDS["good"][1]:
        return COLOR_MAP["good"]
    elif temp_celsius < TEMP_THRESHOLDS["warm"][1]:
        return COLOR_MAP["warm"]
    elif temp_celsius < TEMP_THRESHOLDS["hot"][1]:
        return COLOR_MAP["hot"]
    else:
        return COLOR_MAP["critical"]


def get_temperature_status(temp_celsius: float) -> str:
    """Get human-readable status for temperature.
    
    Args:
        temp_celsius: Temperature in Celsius
        
    Returns:
        Status string (Good, Warm, Hot, Critical)
    """
    if temp_celsius < TEMP_THRESHOLDS["good"][1]:
        return "Good"
    elif temp_celsius < TEMP_THRESHOLDS["warm"][1]:
        return "Warm"
    elif temp_celsius < TEMP_THRESHOLDS["hot"][1]:
        return "Hot"
    else:
        return "Critical"


def format_device_header(status_data: Dict[str, Any]) -> str:
    """Format device info into a single readable header line.
    
    Args:
        status_data: Full device status dict from DeviceStatusMonitor
        
    Returns:
        Formatted header string
    """
    device = status_data.get("device", {})
    arch = device.get("architecture", "Unknown")
    device_id = device.get("device_id", "Unknown")
    fw = device.get("fw_version", "Unknown")
    uptime = format_uptime(status_data.get("uptime_seconds", 0))
    
    return f"{arch} ({device_id}) | FW: {fw} | Uptime: {uptime}"


def format_networks_table(status_data: Dict[str, Any]) -> List[List[str]]:
    """Convert networks data to DataFrame-compatible format.
    
    Args:
        status_data: Full device status dict from DeviceStatusMonitor
        
    Returns:
        List of [name, type, loaded_at, last_used] rows
    """
    networks_data = status_data.get("networks", {})
    networks = networks_data.get("networks", [])
    
    table_rows = []
    for net in networks:
        loaded_at = format_relative_time(net.get("loaded_at", 0))
        last_used = format_relative_time(net.get("last_used", 0))
        
        row = [
            net.get("name", "Unknown"),
            net.get("model_type", "Unknown"),
            loaded_at,
            last_used,
        ]
        table_rows.append(row)
    
    return table_rows


def create_temperature_gauge_html(temp_celsius: float) -> str:
    """Create an SVG gauge widget for temperature display.
    
    Args:
        temp_celsius: Current temperature in Celsius
        
    Returns:
        HTML/SVG markup for temperature gauge
    """
    color = get_temperature_color(temp_celsius)
    status = get_temperature_status(temp_celsius)
    
    return f"""
    <div style="text-align: center; padding: 12px;">
        <svg width="160" height="120" viewBox="0 0 200 150">
            <!-- Background circle -->
            <circle cx="100" cy="90" r="50" fill="none" stroke="#e0e0e0" stroke-width="8"/>
            
            <!-- Colored circle -->
            <circle cx="100" cy="90" r="50" fill="none" stroke="{color}" stroke-width="8"/>
            
            <!-- Center value -->
            <text x="100" y="98" font-size="24" font-weight="bold" text-anchor="middle" fill="{color}">
                {temp_celsius:.1f}°C
            </text>
            <text x="100" y="120" font-size="12" text-anchor="middle" fill="#666">
                {status}
            </text>
        </svg>
    </div>
    """


def create_queue_gauge_html(queue_depth: int) -> str:
    """Create a compact gauge widget for queue depth display.
    
    Args:
        queue_depth: Number of pending requests in queue
        
    Returns:
        HTML/SVG markup for queue gauge
    """
    # Color coding based on queue depth
    if queue_depth == 0:
        color = "#4CAF50"  # Green - idle
        status = "Idle"
    elif queue_depth < 3:
        color = "#FFC107"  # Yellow - light load
        status = "Light"
    elif queue_depth < 10:
        color = "#FF9800"  # Orange - busy
        status = "Busy"
    else:
        color = "#F44336"  # Red - heavy load
        status = "Heavy"
    
    return f"""
    <div style="text-align: center; padding: 12px;">
        <svg width="160" height="120" viewBox="0 0 200 150">
            <!-- Background circle -->
            <circle cx="100" cy="90" r="50" fill="none" stroke="#e0e0e0" stroke-width="8"/>
            
            <!-- Colored circle -->
            <circle cx="100" cy="90" r="50" fill="none" stroke="{color}" stroke-width="8"/>
            
            <!-- Center value -->
            <text x="100" y="98" font-size="32" font-weight="bold" text-anchor="middle" fill="{color}">
                {queue_depth}
            </text>
            <text x="100" y="120" font-size="12" text-anchor="middle" fill="#666">
                {status}
            </text>
        </svg>
    </div>
    """
