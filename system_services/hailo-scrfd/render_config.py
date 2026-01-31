#!/usr/bin/env python3
"""
Render hailo-scrfd YAML config to JSON for hailo-apps compatibility.

Usage:
    python3 render_config.py --input /etc/hailo/hailo-scrfd.yaml --output /etc/xdg/hailo-scrfd/hailo-scrfd.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


def render_config(yaml_path: Path, json_path: Path) -> None:
    """
    Convert YAML config to JSON format.
    
    Args:
        yaml_path: Path to input YAML file
        json_path: Path to output JSON file
    """
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        
        # Transform to hailo-apps JSON format if needed
        json_config: Dict[str, Any] = {
            "model": config.get("scrfd", {}).get("model", "scrfd_2.5g_bnkps"),
            "input_size": config.get("scrfd", {}).get("input_size", 640),
            "conf_threshold": config.get("scrfd", {}).get("conf_threshold", 0.5),
            "nms_threshold": config.get("scrfd", {}).get("nms_threshold", 0.4),
            "device": config.get("scrfd", {}).get("device", 0),
        }
        
        # Ensure parent directory exists
        json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON config
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_config, f, indent=2)
        
        print(f"Rendered config: {yaml_path} -> {json_path}")
        
    except Exception as e:
        print(f"Error rendering config: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Render SCRFD YAML config to JSON")
    parser.add_argument("--input", required=True, help="Input YAML config path")
    parser.add_argument("--output", required=True, help="Output JSON config path")
    
    args = parser.parse_args()
    
    yaml_path = Path(args.input)
    json_path = Path(args.output)
    
    if not yaml_path.exists():
        print(f"Error: Input file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)
    
    render_config(yaml_path, json_path)


if __name__ == "__main__":
    main()
