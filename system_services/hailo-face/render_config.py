#!/usr/bin/env python3
"""
Render hailo-face config.yaml for installation.

Reads config.yaml template and renders it with configurable values.
"""

import os
import sys
import yaml
from pathlib import Path


def render_config(template_path: str, output_path: str, overrides: dict = None):
    """
    Render configuration file with optional overrides.
    
    Args:
        template_path: Path to config.yaml template
        output_path: Path to write rendered config
        overrides: Optional dict of config overrides
    """
    # Load template
    with open(template_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Apply overrides if provided
    if overrides:
        for key_path, value in overrides.items():
            # Support nested keys like "server.port"
            keys = key_path.split('.')
            target = config
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = value
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Write rendered config
    with open(output_path, 'w') as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"Rendered config: {output_path}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: render_config.py <output_path> [key=value ...]")
        print("Example: render_config.py /etc/hailo/hailo-face.yaml server.port=5002")
        sys.exit(1)
    
    script_dir = Path(__file__).parent
    template_path = script_dir / "config.yaml"
    output_path = sys.argv[1]
    
    # Parse overrides from command line
    overrides = {}
    for arg in sys.argv[2:]:
        if '=' in arg:
            key, value = arg.split('=', 1)
            # Try to parse as int/float/bool
            if value.lower() in ('true', 'false'):
                value = value.lower() == 'true'
            else:
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass  # Keep as string
            
            overrides[key] = value
    
    render_config(str(template_path), output_path, overrides)


if __name__ == '__main__':
    main()
