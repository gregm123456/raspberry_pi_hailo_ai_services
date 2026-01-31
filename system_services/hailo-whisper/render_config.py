#!/usr/bin/env python3
"""
Render YAML config to JSON for hailo-whisper service.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip3 install pyyaml or sudo apt install python3-yaml")
    sys.exit(1)


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
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON config
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
