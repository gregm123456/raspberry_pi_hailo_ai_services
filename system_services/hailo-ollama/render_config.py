#!/usr/bin/env python3
"""Render hailo-ollama YAML config to upstream JSON config."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - install-time dependency
    raise SystemExit(
        "PyYAML is required. Install with: sudo apt install python3-yaml"
    ) from exc

DEFAULTS = {
    "server": {"host": "0.0.0.0", "port": 11434},
    "library": {"host": "dev-public.hailo.ai", "port": 443},
    "main_poll_time_ms": 200,
}


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_yaml(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")
    return data


def _render_config(data: dict[str, Any]) -> dict[str, Any]:
    server = data.get("server", {}) if isinstance(data.get("server"), dict) else {}
    library = data.get("library", {}) if isinstance(data.get("library"), dict) else {}

    server_host = server.get("host", DEFAULTS["server"]["host"])
    server_port = _coerce_int(server.get("port"), DEFAULTS["server"]["port"])

    library_host = library.get("host", DEFAULTS["library"]["host"])
    library_port = _coerce_int(library.get("port"), DEFAULTS["library"]["port"])

    poll_time = _coerce_int(
        data.get("main_poll_time_ms"), DEFAULTS["main_poll_time_ms"]
    )

    return {
        "server": {"host": server_host, "port": server_port},
        "library": {"host": library_host, "port": library_port},
        "main_poll_time_ms": poll_time,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render hailo-ollama JSON config")
    parser.add_argument(
        "--input",
        default="/etc/hailo/hailo-ollama.yaml",
        help="Path to YAML config (default: /etc/hailo/hailo-ollama.yaml)",
    )
    parser.add_argument(
        "--output",
        default="/etc/xdg/hailo-ollama/hailo-ollama.json",
        help="Path to JSON config (default: /etc/xdg/hailo-ollama/hailo-ollama.json)",
    )
    args = parser.parse_args()

    data = _load_yaml(args.input)
    rendered = _render_config(data)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(rendered, handle, indent=2)
        handle.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
