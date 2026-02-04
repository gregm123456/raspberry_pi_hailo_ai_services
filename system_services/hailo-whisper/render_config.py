#!/usr/bin/env python3
"""Render YAML config to JSON for hailo-whisper service."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip3 install pyyaml or sudo apt install python3-yaml")
    sys.exit(1)


def _validate_config(config: Dict[str, Any]) -> None:
    required_sections = ["server", "model", "transcription", "storage"]
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required section: {section}")

    server = config.get("server", {})
    if not isinstance(server, dict) or "host" not in server or "port" not in server:
        raise ValueError("'server' must include 'host' and 'port'")

    model = config.get("model", {})
    if not isinstance(model, dict) or "name" not in model:
        raise ValueError("'model' must include 'name'")

    transcription = config.get("transcription", {})
    if not isinstance(transcription, dict):
        raise ValueError("'transcription' must be a dictionary")

    storage = config.get("storage", {})
    if not isinstance(storage, dict) or "cache_dir" not in storage:
        raise ValueError("'storage' must include 'cache_dir'")


def render_config(input_path: Path, output_path: Path):
    """Convert YAML config to JSON."""
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not isinstance(config, dict):
            print("Error: Config must be a YAML dictionary", file=sys.stderr)
            sys.exit(1)
        
        _validate_config(config)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"Config rendered: {output_path}")
        
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Render YAML config to JSON')
    parser.add_argument('--input', type=Path, required=True, help='Input YAML file')
    parser.add_argument('--output', type=Path, required=True, help='Output JSON file')
    
    args = parser.parse_args()
    render_config(args.input, args.output)


if __name__ == '__main__':
    main()
