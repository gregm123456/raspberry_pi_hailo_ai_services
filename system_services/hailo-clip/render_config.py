#!/usr/bin/env python3
"""
Render hailo-clip YAML config to JSON format.
YAML -> JSON conversion with validation.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml


def render_config(yaml_path: str, json_path: str) -> bool:
    """
    Load YAML config, validate, and render to JSON.
    
    Args:
        yaml_path: Path to input YAML config
        json_path: Path to output JSON config
        
    Returns:
        True on success, False on error
    """
    try:
        # Load YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        
        if not isinstance(config, dict):
            print(f"ERROR: Config must be a dict, got {type(config)}", file=sys.stderr)
            return False
        
        # Validate required keys
        if "server" not in config:
            print("ERROR: Missing 'server' section", file=sys.stderr)
            return False
        
        # Ensure required server fields
        server = config.get("server", {})
        if not isinstance(server, dict):
            print("ERROR: 'server' must be a dict", file=sys.stderr)
            return False
        
        server.setdefault("host", "0.0.0.0")
        server.setdefault("port", 5000)
        server.setdefault("debug", False)
        
        # Ensure CLIP config
        clip_cfg = config.get("clip", {})
        if not isinstance(clip_cfg, dict):
            print("ERROR: 'clip' must be a dict", file=sys.stderr)
            return False
        
        clip_cfg.setdefault("model", "clip-resnet-50x4")
        clip_cfg.setdefault("embedding_dimension", 640)
        clip_cfg.setdefault("device", 0)
        clip_cfg.setdefault("image_size", 224)
        clip_cfg.setdefault("batch_size", 1)
        clip_cfg.setdefault("device_timeout_ms", 5000)
        
        # Create output directory if needed
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        
        print(f"Rendered config to {json_path}", file=sys.stderr)
        return True
        
    except FileNotFoundError:
        print(f"ERROR: File not found: {yaml_path}", file=sys.stderr)
        return False
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Render hailo-clip YAML config to JSON"
    )
    parser.add_argument("--input", required=True, help="Input YAML config")
    parser.add_argument("--output", required=True, help="Output JSON config")
    
    args = parser.parse_args()
    
    if not render_config(args.input, args.output):
        sys.exit(1)


if __name__ == "__main__":
    main()
