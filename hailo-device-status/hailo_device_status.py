#!/usr/bin/env python3
"""
Hailo Device Status Utility

Queries Hailo-10H NPU device status via HailoRT Python API.
Exposes device info, firmware version, loaded networks, and temperature.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Any, Optional
import click
from hailo_platform import Device, VDevice

# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[36m"


DEFAULT_DEVICE_STATUS_URL = "http://127.0.0.1:5099"
DEFAULT_HTTP_TIMEOUT = 0.5
_DISABLED_VALUES = {"0", "off", "false", "none", "disable", "disabled"}


def _get_manager_status_http() -> Optional[Dict[str, Any]]:
    base_url = os.environ.get("HAILO_DEVICE_STATUS_URL", DEFAULT_DEVICE_STATUS_URL)
    if base_url.strip().lower() in _DISABLED_VALUES:
        return None

    timeout_value = os.environ.get("HAILO_DEVICE_STATUS_TIMEOUT")
    try:
        timeout = float(timeout_value) if timeout_value else DEFAULT_HTTP_TIMEOUT
    except ValueError:
        timeout = DEFAULT_HTTP_TIMEOUT

    url = f"{base_url.rstrip('/')}/v1/device/status"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None


def _device_data_from_manager(manager_status: Dict[str, Any]) -> Dict[str, Any]:
    device = manager_status.get("device") or {}
    device_info = {
        "index": 0,
        "device_id": device.get("device_id"),
        "architecture": device.get("architecture"),
        "fw_version": device.get("fw_version"),
        "temperature_celsius": device.get("temperature_celsius"),
    }
    if "temperature_error" in device:
        device_info["temperature_error"] = device.get("temperature_error")

    return {
        "status": "ok" if device else "error",
        "device_count": 1 if device else 0,
        "devices": [device_info] if device else [],
    }


def _networks_data_from_manager(manager_status: Dict[str, Any]) -> Dict[str, Any]:
    networks = manager_status.get("networks") or {}
    return {
        "status": networks.get("status", "ok"),
        "network_count": networks.get("network_count", 0),
        "networks": networks.get("networks", []),
        "source": "device_manager_http",
        "scope": "global",
    }


def get_device_info() -> Dict[str, Any]:
    """
    Query device information using HailoRT Python API.
    
    Returns:
        Dictionary with device properties:
        - device_id: Physical device ID
        - architecture: Device architecture string
        - fw_version: Firmware version
        - temperature: Device temperature (if available)
        - status: Overall status
    
    Note: Device.scan() returns device ID strings, not device objects.
    We create Device objects from those IDs to access control info.
    """
    try:
        device_ids = Device.scan()
        if not device_ids:
            return {
                "status": "error",
                "message": "No Hailo devices detected",
                "device_count": 0,
                "devices": []
            }
        
        result = {
            "status": "ok",
            "device_count": len(device_ids),
            "devices": []
        }
        
        for idx, device_id in enumerate(device_ids):
            device = Device(device_id)
            board_info = device.control.identify()
            
            device_info = {
                "index": idx,
                "device_id": device.device_id,
                "architecture": str(board_info.device_architecture),
                "fw_version": str(board_info.firmware_version),
            }
            
            # Attempt to get temperature
            try:
                temp_info = device.control.get_chip_temperature()
                # Use the primary temperature sensor (ts0)
                device_info["temperature_celsius"] = round(temp_info.ts0_temperature, 1)
            except Exception as e:
                device_info["temperature_celsius"] = None
                device_info["temperature_error"] = str(e)
            
            # Include loaded networks for this device
            device_info["loaded_networks"] = device.loaded_network_groups
            
            result["devices"].append(device_info)
            device.release()
        
        return result
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to scan devices: {str(e)}",
            "device_count": 0,
            "devices": []
        }


def get_loaded_networks() -> Dict[str, Any]:
    """
    Query networks loaded by this process via Device API.
    
    LIMITATION: Only shows networks loaded by THIS PROCESS.
    Networks loaded by other processes (e.g., device_manager, concurrent tests)
    are not visible to this Device instance. This is an HailoRT architecture constraint.
    
    For global device status across all processes, use device_manager's API
    (Phase 2 feature: /v1/device/status).
    
    Returns:
        Dictionary with network info:
        - network_count: Number of networks loaded by this process only
        - networks: List of network names
        - source: Where data came from (VDevice or Device direct)
    """
    try:
        # Try VDevice first (preferred when device_manager owns the device)
        device_ids = Device.scan()
        if device_ids:
            vdevice = VDevice(device_ids)
            network_groups = vdevice.get_network_groups()
            
            networks = []
            if network_groups:
                for ng in network_groups:
                    networks.append({
                        "name": ng.name,
                        "input_count": len(ng.input_layers),
                        "output_count": len(ng.output_layers),
                    })
            
            return {
                "status": "ok",
                "network_count": len(networks),
                "networks": networks,
                "source": "VDevice",
                "scope": "this process",
            }
    
    except Exception as vdevice_error:
        # VDevice not available, try direct device access
        try:
            device_ids = Device.scan()
            if not device_ids:
                return {
                    "status": "unavailable",
                    "network_count": 0,
                    "networks": [],
                    "source": "No devices found",
                }
            
            device = Device(device_ids[0])
            networks = []
            for ng in device.loaded_network_groups:
                networks.append({
                    "name": ng.name,
                    "input_count": len(ng.input_layers),
                    "output_count": len(ng.output_layers),
                })
            
            device.release()
            
            return {
                "status": "ok",
                "network_count": len(networks),
                "networks": networks,
                "source": "Device (direct access)",
                "scope": "this process",
            }
        
        except Exception as device_error:
            # Both approaches failed
            return {
                "status": "unavailable",
                "network_count": 0,
                "networks": [],
                "source": "VDevice/Device unavailable",
                "note": "Device manager may not be running or device is busy."
            }


def get_manager_status() -> Optional[Dict[str, Any]]:
    return _get_manager_status_http()


def format_device_output(device_data: Dict[str, Any], json_output: bool = False) -> str:
    """Format device info for display."""
    if json_output:
        return json.dumps(device_data, indent=2)
    
    if device_data["status"] == "error":
        return f"{Colors.RED}✗ Error: {device_data['message']}{Colors.RESET}"
    
    output = []
    output.append(f"{Colors.BOLD}{Colors.CYAN}Hailo Devices{Colors.RESET}")
    output.append(f"Found: {device_data['device_count']} device(s)\n")
    
    for dev in device_data["devices"]:
        output.append(f"{Colors.BOLD}Device {dev['index']}:{Colors.RESET}")
        output.append(f"  Device ID:     {dev['device_id']}")
        output.append(f"  Architecture:  {dev['architecture']}")
        output.append(f"  Firmware:      {dev['fw_version']}")
        
        if dev.get("temperature_celsius") is not None:
            temp = dev["temperature_celsius"]
            if temp > 80:
                color = Colors.RED
            elif temp > 65:
                color = Colors.YELLOW
            else:
                color = Colors.GREEN
            output.append(f"  Temperature:   {color}{temp:.1f}°C{Colors.RESET}")
        else:
            output.append(f"  Temperature:   {Colors.YELLOW}(unavailable){Colors.RESET}")
        
        output.append("")
    
    return "\n".join(output)


def format_networks_output(networks_data: Dict[str, Any], json_output: bool = False) -> str:
    """Format loaded networks for display."""
    if json_output:
        return json.dumps(networks_data, indent=2)
    
    output = []
    output.append(f"{Colors.BOLD}{Colors.CYAN}Loaded Networks{Colors.RESET}")
    count_line = f"Count: {networks_data['network_count']}"
    scope = networks_data.get("scope")
    if scope:
        count_line = f"{count_line} ({scope})"
    output.append(count_line)
    output.append(f"Source: {networks_data.get('source', 'unknown')}\n")

    if networks_data['network_count'] == 0:
        if networks_data.get('status') == 'unavailable':
            note = networks_data.get('note', 'Network status unavailable')
            output.append(f"{Colors.YELLOW}ℹ {note}{Colors.RESET}")
        elif scope == "this process":
            output.append(f"{Colors.YELLOW}ℹ No networks loaded by this process.{Colors.RESET}")
            output.append(f"{Colors.YELLOW}  Networks loaded by other processes are not visible here.{Colors.RESET}")
            output.append(f"{Colors.YELLOW}  Use device_manager's /v1/device/status to see all loaded networks.{Colors.RESET}")
        else:
            output.append(f"{Colors.YELLOW}ℹ No networks reported.{Colors.RESET}")
    else:
        for net in networks_data['networks']:
            name = net.get('name', 'unknown')
            output.append(f"{Colors.BOLD}{name}{Colors.RESET}")
            if 'input_count' in net and 'output_count' in net:
                output.append(f"  Inputs:  {net['input_count']}")
                output.append(f"  Outputs: {net['output_count']}")
            else:
                if net.get('model_type'):
                    output.append(f"  Type:   {net['model_type']}")
                if net.get('model_path'):
                    output.append(f"  Path:   {net['model_path']}")
            output.append("")
    
    return "\n".join(output)


@click.group()
@click.version_option()
def cli():
    """
    Hailo Device Status Utility
    
    Query Hailo-10H NPU device status including firmware, architecture,
    loaded networks, and temperature information.
    """
    pass


@cli.command()
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def device(json_output: bool):
    """Show device information."""
    manager_status = get_manager_status()
    if manager_status:
        device_data = _device_data_from_manager(manager_status)
    else:
        device_data = get_device_info()

    output = format_device_output(device_data, json_output)
    click.echo(output)

    # Exit with error code if device detection failed
    if device_data["status"] == "error":
        sys.exit(1)


@cli.command()
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def networks(json_output: bool):
    """Show networks loaded by this process.
    
    Note: Only shows networks loaded by this utility instance.
    Networks loaded by other processes are not visible here.
    """
    manager_status = get_manager_status()
    if manager_status:
        networks_data = _networks_data_from_manager(manager_status)
    else:
        networks_data = get_loaded_networks()

    output = format_networks_output(networks_data, json_output)
    click.echo(output)


@cli.command()
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def status(json_output: bool):
    """Show complete device status (device info + networks)."""
    manager_status = get_manager_status()
    if manager_status:
        device_data = _device_data_from_manager(manager_status)
        networks_data = _networks_data_from_manager(manager_status)
        source = "device_manager_http"
    else:
        device_data = get_device_info()
        networks_data = get_loaded_networks()
        source = "direct"

    combined = {
        "status": "ok" if device_data["status"] == "ok" else "error",
        "devices": device_data,
        "networks": networks_data,
        "source": source,
    }
    
    if json_output:
        output = json.dumps(combined, indent=2)
        click.echo(output)
    else:
        output = []
        output.append(format_device_output(device_data, json_output=False))
        output.append("")
        output.append(format_networks_output(networks_data, json_output=False))
        click.echo("\n".join(output))
    
    # Exit with error code if device detection failed
    if device_data["status"] == "error":
        sys.exit(1)


@cli.command()
def health():
    """Quick health check (exit 0 if device accessible, 1 otherwise)."""
    manager_status = get_manager_status()
    if manager_status:
        device_data = _device_data_from_manager(manager_status)
    else:
        device_data = get_device_info()

    if device_data["status"] == "ok" and device_data["device_count"] > 0:
        click.echo(f"{Colors.GREEN}✓ Device accessible{Colors.RESET}")
        sys.exit(0)
    else:
        click.echo(f"{Colors.RED}✗ Device not accessible{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
