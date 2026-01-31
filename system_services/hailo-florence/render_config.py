#!/usr/bin/env python3
"""
Configuration renderer for hailo-florence service.

This script processes the config.yaml template and renders it with
environment-specific values or user overrides.
"""

import os
import sys
import yaml
from pathlib import Path


def render_config(template_path, output_path, overrides=None):
    """
    Render configuration template with optional overrides.
    
    Args:
        template_path: Path to config.yaml template
        output_path: Path to write rendered config
        overrides: Optional dict of values to override
    """
    # Load template
    with open(template_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Apply overrides if provided
    if overrides:
        config = deep_merge(config, overrides)
    
    # Environment variable substitutions
    config = substitute_env_vars(config)
    
    # Write rendered config
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"Configuration rendered: {output_path}")
    return config


def deep_merge(base, override):
    """Recursively merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def substitute_env_vars(config):
    """Substitute ${ENV_VAR} placeholders with environment variables."""
    if isinstance(config, dict):
        return {k: substitute_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [substitute_env_vars(item) for item in config]
    elif isinstance(config, str):
        # Simple ${VAR} substitution
        if config.startswith('${') and config.endswith('}'):
            var_name = config[2:-1]
            return os.getenv(var_name, config)
        return config
    else:
        return config


def validate_config(config):
    """Validate configuration values."""
    errors = []
    
    # Required sections
    required_sections = ['service', 'model', 'resources']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required section: {section}")
    
    # Service validation
    if 'service' in config:
        port = config['service'].get('port')
        if port and (port < 1024 or port > 65535):
            errors.append(f"Invalid port: {port} (must be 1024-65535)")
    
    # Model validation
    if 'model' in config:
        max_length = config['model'].get('max_length', 100)
        min_length = config['model'].get('min_length', 10)
        if max_length < min_length:
            errors.append(f"max_length ({max_length}) must be >= min_length ({min_length})")
    
    # Resource validation
    if 'resources' in config:
        timeout = config['resources'].get('request_timeout_seconds', 30)
        if timeout <= 0:
            errors.append(f"Invalid request_timeout_seconds: {timeout}")
    
    if errors:
        print("Configuration validation errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    
    print("Configuration validation: OK")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Render hailo-florence configuration")
    parser.add_argument(
        '--template',
        default='config.yaml',
        help='Path to config template (default: config.yaml)'
    )
    parser.add_argument(
        '--output',
        default='/etc/hailo/florence/config.yaml',
        help='Path to write rendered config (default: /etc/hailo/florence/config.yaml)'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate configuration, do not write'
    )
    parser.add_argument(
        '--set',
        action='append',
        metavar='KEY=VALUE',
        help='Override configuration value (e.g., --set service.port=8083)'
    )
    
    args = parser.parse_args()
    
    # Parse overrides
    overrides = {}
    if args.set:
        for override in args.set:
            if '=' not in override:
                print(f"Invalid override format: {override}", file=sys.stderr)
                print("Expected: KEY=VALUE (e.g., service.port=8083)", file=sys.stderr)
                sys.exit(1)
            
            key_path, value = override.split('=', 1)
            keys = key_path.split('.')
            
            # Build nested dict
            current = overrides
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Try to parse value as int/float/bool
            try:
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                elif value.isdigit():
                    value = int(value)
                elif '.' in value and all(part.isdigit() for part in value.split('.', 1)):
                    value = float(value)
            except:
                pass  # Keep as string
            
            current[keys[-1]] = value
    
    # Render configuration
    config = render_config(args.template, args.output, overrides)
    
    # Validate
    validate_config(config)
    
    if not args.validate_only:
        print(f"Configuration written to: {args.output}")


if __name__ == '__main__':
    main()
