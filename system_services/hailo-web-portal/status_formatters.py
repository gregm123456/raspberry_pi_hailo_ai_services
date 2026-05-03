"""Status formatters for dashboard display.

Converts raw device status data into formatted, human-readable components
for the Hailo Web Portal dashboard.
"""

from __future__ import annotations

import os
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


_MODEL_COLORS = [
    "#4CAF50",
    "#03A9F4",
    "#FFC107",
    "#FF7043",
    "#AB47BC",
    "#26A69A",
    "#EC407A",
    "#8D6E63",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_model_weights(networks: List[Dict[str, Any]]) -> List[float]:
    """Estimate relative memory weight per loaded model.

    Uses model-profile heuristics first (name + type), then a bounded
    file-size fallback. Raw HEF size alone can be misleading for runtime VRAM.
    """
    # Relative weights tuned for common service models on Hailo-10H.
    # They represent proportional share, not absolute MB.
    type_fallback = {
        "vlm_chat": 8.0,
        "vlm": 5.5,
        "whisper": 2.3,
        "clip": 1.2,
        "ocr": 1.4,
        "pose": 1.0,
        "depth": 1.0,
    }

    model_overrides = [
        ("qwen2-vl-2b", 10.0),
        ("whisper-base", 2.4),
        ("whisper", 2.2),
        ("clip_vit_b_32", 1.1),
        ("ocr_det", 1.4),
        ("ocr.hef", 1.0),
        ("yolov8s_pose", 1.0),
        ("scdepthv3", 1.0),
    ]

    weights: List[float] = []
    for net in networks:
        model_path = str(net.get("model_path", ""))
        model_type = str(net.get("model_type", ""))
        model_name = str(net.get("name", ""))
        model_id = f"{model_name} {model_path}".lower()

        override_weight = None
        for needle, weight in model_overrides:
            if needle in model_id:
                override_weight = weight
                break

        if override_weight is not None:
            weights.append(override_weight)
            continue

        file_weight = 0.0
        if model_path and os.path.exists(model_path):
            try:
                file_weight = float(os.path.getsize(model_path)) / (1024.0 * 1024.0)
            except OSError:
                file_weight = 0.0

        if file_weight > 0.0:
            # Compress and bound file-size influence to avoid extreme skew.
            bounded = max(0.6, min((file_weight ** 0.5) / 2.0, 4.0))
            # Keep strong type prior while still using file-size as a hint.
            type_weight = type_fallback.get(model_type, 1.0)
            weights.append((type_weight * 0.8) + (bounded * 0.2))
        else:
            weights.append(type_fallback.get(model_type, 1.0))

    return weights


def create_ram_overview_html(status_data: Dict[str, Any]) -> str:
    """Create a top-level RAM usage panel with segmented per-model bar."""
    monitor = status_data.get("monitor", {})
    ram = monitor.get("ram", {})
    perf = monitor.get("performance", {})
    networks_data = status_data.get("networks", {})
    networks = networks_data.get("networks", [])

    used_mb = _safe_float(ram.get("used_mb"), 0.0)
    total_mb = _safe_float(ram.get("total_mb"), 0.0)
    util_pct = _safe_float(ram.get("utilization_percent"), 0.0)
    free_mb = max(total_mb - used_mb, 0.0)

    if total_mb <= 0.0:
        return """
        <div style="padding:10px 14px;border:1px solid #2f3138;border-radius:8px;background:#111318;color:#c9ccd4;">
          <div style="font-size:13px;font-weight:600;margin-bottom:4px;">NPU Memory</div>
          <div style="font-size:12px;opacity:0.85;">RAM metrics unavailable (hailortcli monitor not ready).</div>
        </div>
        """

    free_pct = (free_mb / total_mb) * 100.0 if total_mb > 0 else 0.0
    weights = _estimate_model_weights(networks)
    weight_sum = sum(weights)

    segments_html: List[str] = []
    legend_html: List[str] = []
    overhead_color = "#596275"
    overhead_mb = used_mb

    if networks and used_mb > 0.0 and weight_sum > 0.0:
        # Reserve a visible runtime-overhead bucket so one model does not absorb
        # all shared runtime costs in the visualization.
        overhead_fraction = max(0.12, min(0.35 - (0.04 * len(networks)), 0.35))
        overhead_mb = max(used_mb * overhead_fraction, min(used_mb, 220.0))
        overhead_mb = min(overhead_mb, used_mb * 0.45)
        model_budget_mb = max(used_mb - overhead_mb, 0.0)

        for idx, net in enumerate(networks):
            color = _MODEL_COLORS[idx % len(_MODEL_COLORS)]
            fraction = weights[idx] / weight_sum
            est_mb = model_budget_mb * fraction
            pct_total = (est_mb / total_mb) * 100.0
            name = str(net.get("name", "unknown"))
            model_type = str(net.get("model_type", "unknown"))

            segments_html.append(
                f'<div title="{name} ({model_type}): ~{est_mb:.0f} MB" '
                f'style="height:100%;width:{pct_total:.2f}%;background:{color};"></div>'
            )
            legend_html.append(
                "<div style=\"display:flex;align-items:center;gap:6px;font-size:11px;color:#c9ccd4;\">"
                f"<span style=\"display:inline-block;width:9px;height:9px;border-radius:2px;background:{color};\"></span>"
                f"<span>{name}</span>"
                f"<span style=\"opacity:0.75;\">~{est_mb:.0f} MB</span>"
                "</div>"
            )

        segments_html.append(
            f'<div title="Runtime overhead: ~{overhead_mb:.0f} MB" '
            f'style="height:100%;width:{(overhead_mb / total_mb) * 100.0:.2f}%;background:{overhead_color};"></div>'
        )
        legend_html.append(
            "<div style=\"display:flex;align-items:center;gap:6px;font-size:11px;color:#c9ccd4;\">"
            f"<span style=\"display:inline-block;width:9px;height:9px;border-radius:2px;background:{overhead_color};\"></span>"
            "<span>Runtime overhead</span>"
            f"<span style=\"opacity:0.75;\">~{overhead_mb:.0f} MB</span>"
            "</div>"
        )
    elif used_mb > 0.0:
        # No model list available; treat all used memory as runtime overhead.
        segments_html.append(
            f'<div title="Runtime overhead: ~{used_mb:.0f} MB" '
            f'style="height:100%;width:{(used_mb / total_mb) * 100.0:.2f}%;background:{overhead_color};"></div>'
        )
        legend_html.append(
            "<div style=\"display:flex;align-items:center;gap:6px;font-size:11px;color:#c9ccd4;\">"
            f"<span style=\"display:inline-block;width:9px;height:9px;border-radius:2px;background:{overhead_color};\"></span>"
            "<span>Runtime overhead</span>"
            f"<span style=\"opacity:0.75;\">~{used_mb:.0f} MB</span>"
            "</div>"
        )

    # Free segment is always shown at the end.
    segments_html.append(
        f'<div title="Free: {free_mb:.0f} MB" '
        f'style="height:100%;width:{free_pct:.2f}%;background:#3a3f4b;"></div>'
    )

    nnc_util = _safe_float(perf.get("nnc_utilization_percent"), 0.0)
    cpu_util = _safe_float(perf.get("cpu_utilization_percent"), 0.0)

    legend_block = "".join(legend_html)
    if not legend_block:
        legend_block = (
            "<div style=\"font-size:11px;color:#c9ccd4;opacity:0.8;\">"
            "No loaded models to estimate memory split.</div>"
        )

    capacity_reason = status_data.get("last_capacity_event_reason")
    capacity_model = status_data.get("last_capacity_event_model")
    capacity_note = ""
    if capacity_reason:
        model_suffix = f" ({os.path.basename(str(capacity_model))})" if capacity_model else ""
        capacity_note = (
            "<div style=\"margin-top:6px;font-size:10px;color:#ffcc80;\">"
            f"Last capacity event: {capacity_reason}{model_suffix}"
            "</div>"
        )

    return f"""
    <div style="padding:10px 14px;border:1px solid #2f3138;border-radius:8px;background:#111318;color:#c9ccd4;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;">
        <div style="font-size:13px;font-weight:600;">NPU Memory</div>
        <div style="font-size:11px;opacity:0.85;">NNC {nnc_util:.1f}% | CPU {cpu_util:.1f}% | RAM {util_pct:.1f}%</div>
      </div>
      <div style="margin-top:6px;font-size:12px;opacity:0.9;">Used {used_mb:.0f} MB / {total_mb:.0f} MB, Free {free_mb:.0f} MB</div>
      <div style="margin-top:8px;height:16px;border-radius:4px;overflow:hidden;background:#1d212b;display:flex;">
        {''.join(segments_html)}
      </div>
      <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:10px 16px;">
        {legend_block}
        <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#c9ccd4;">
          <span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:#3a3f4b;"></span>
          <span>Free</span>
          <span style="opacity:0.75;">{free_mb:.0f} MB</span>
        </div>
      </div>
      <div style="margin-top:6px;font-size:10px;opacity:0.65;">Per-model values are estimated from loaded HEF artifacts and model type.</div>
            {capacity_note}
    </div>
    """
