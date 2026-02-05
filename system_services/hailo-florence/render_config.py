#!/usr/bin/env python3
"""Render hailo-florence YAML config to JSON format."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


def _validate_config(config: Dict[str, Any]) -> None:
    required_sections = ["server", "model", "resources"]
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required section: {section}")

    server = config.get("server", {})
    if not isinstance(server, dict) or "host" not in server or "port" not in server:
        raise ValueError("'server' must include 'host' and 'port'")

    port = int(server.get("port", 0))
    if port < 1024 or port > 65535:
        raise ValueError(f"Invalid port: {port} (must be 1024-65535)")

    model = config.get("model", {})
    if not isinstance(model, dict) or "model_dir" not in model:
        raise ValueError("'model' must include 'model_dir'")

    max_length = int(model.get("max_length", 100))
    min_length = int(model.get("min_length", 10))
    if max_length < min_length:
        raise ValueError("model.max_length must be >= model.min_length")

    resources = config.get("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("'resources' must be a dictionary")

    timeout = int(resources.get("request_timeout_seconds", 30))
    if timeout <= 0:
        raise ValueError("resources.request_timeout_seconds must be > 0")


def render_config(input_path: Path, output_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    if not isinstance(config, dict):
        raise ValueError("Config must be a YAML dictionary")

    _validate_config(config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)

    print(f"Config rendered: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render hailo-florence config")
    parser.add_argument(
        "--input",
        default="/etc/hailo/hailo-florence.yaml",
        help="Path to input YAML config",
    )
    parser.add_argument(
        "--output",
        default="/etc/xdg/hailo-florence/hailo-florence.json",
        help="Path to output JSON config",
    )

    args = parser.parse_args()
    try:
        render_config(Path(args.input), Path(args.output))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
