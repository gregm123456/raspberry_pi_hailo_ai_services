#!/usr/bin/env python3
"""
render_config.py - Convert YAML config to JSON

Usage:
    python3 render_config.py --input config.yaml --output config.json
"""

import sys
import json
import yaml
from pathlib import Path
from typing import Any, Dict

def load_yaml(path: str) -> Dict[str, Any]:
    """Load YAML configuration."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Failed to parse YAML: {e}")

def save_json(data: Dict[str, Any], path: str) -> None:
    """Save configuration as JSON."""
    try:
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise RuntimeError(f"Failed to write JSON: {e}")

def validate_schema(config: Dict[str, Any]) -> None:
    """Validate configuration schema."""
    required_sections = ['server', 'model', 'inference', 'pose']
    
    for section in required_sections:
        if section not in config:
            raise RuntimeError(f"Missing required section: {section}")
    
    # Validate server section
    server = config.get('server', {})
    if not isinstance(server, dict):
        raise RuntimeError("'server' must be a dictionary")
    if 'host' not in server or 'port' not in server:
        raise RuntimeError("'server' must have 'host' and 'port'")
    
    # Validate model section
    model = config.get('model', {})
    if not isinstance(model, dict):
        raise RuntimeError("'model' must be a dictionary")
    if 'name' not in model:
        raise RuntimeError("'model' must have 'name'")
    
    # Validate inference section
    inference = config.get('inference', {})
    if not isinstance(inference, dict):
        raise RuntimeError("'inference' must be a dictionary")
    
    # Validate pose section
    pose = config.get('pose', {})
    if not isinstance(pose, dict):
        raise RuntimeError("'pose' must be a dictionary")

def render_config(input_path: str, output_path: str) -> None:
    """Load YAML, validate, and save as JSON."""
    print(f"Loading YAML from: {input_path}")
    config = load_yaml(input_path)
    
    print("Validating schema...")
    validate_schema(config)
    
    print(f"Writing JSON to: {output_path}")
    save_json(config, output_path)
    
    print("✓ Config rendered successfully")

def main() -> int:
    if len(sys.argv) < 5:
        print("Usage: python3 render_config.py --input INPUT.yaml --output OUTPUT.json")
        return 1
    
    input_path = None
    output_path = None
    
    for i, arg in enumerate(sys.argv[1:]):
        if arg == '--input' and i + 1 < len(sys.argv) - 1:
            input_path = sys.argv[i + 2]
        elif arg == '--output' and i + 1 < len(sys.argv) - 1:
            output_path = sys.argv[i + 2]
    
    if not input_path or not output_path:
        print("Error: Missing --input or --output argument")
        print("Usage: python3 render_config.py --input INPUT.yaml --output OUTPUT.json")
        return 1
    
    try:
        render_config(input_path, output_path)
        return 0
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
