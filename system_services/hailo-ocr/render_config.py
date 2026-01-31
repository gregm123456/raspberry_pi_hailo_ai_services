#!/usr/bin/env python3
"""
Render YAML configuration to JSON for hailo-ocr service.

This script converts user-friendly YAML config to JSON format used by the service.
Run by install.sh to validate and convert config on each install/update.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: sudo apt install python3-yaml", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Render hailo-ocr YAML config to JSON"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input YAML config file (e.g., /etc/hailo/hailo-ocr.yaml)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON config file (e.g., /etc/xdg/hailo-ocr/hailo-ocr.json)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate YAML without writing output",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        # Read and parse YAML
        with open(input_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if config is None:
            config = {}

        # Validate required fields
        if not isinstance(config, dict):
            print(f"ERROR: Config must be a dictionary, got {type(config)}", file=sys.stderr)
            sys.exit(1)

        # Apply defaults
        config.setdefault("server", {})
        config.setdefault("ocr", {})
        config.setdefault("processing", {})
        config.setdefault("resource_limits", {})

        # Set default values
        config["server"].setdefault("host", "0.0.0.0")
        config["server"].setdefault("port", 11436)

        config["ocr"].setdefault("languages", ["en"])
        config["ocr"].setdefault("use_gpu", False)
        config["ocr"].setdefault("enable_recognition", True)
        config["ocr"].setdefault("det_threshold", 0.3)
        config["ocr"].setdefault("rec_threshold", 0.5)

        config["processing"].setdefault("max_image_size", 4096)
        config["processing"].setdefault("jpeg_quality", 90)
        config["processing"].setdefault("enable_caching", False)
        config["processing"].setdefault("cache_ttl_seconds", 3600)
        config["processing"].setdefault("max_cache_size_mb", 500)

        config["resource_limits"].setdefault("memory_max", "2.5G")
        config["resource_limits"].setdefault("cpu_quota", "75%")

        # Validate key values
        try:
            port = int(config["server"]["port"])
            if not (1 <= port <= 65535):
                raise ValueError(f"Port {port} out of range (1-65535)")
        except (ValueError, TypeError) as e:
            print(f"ERROR: Invalid port: {e}", file=sys.stderr)
            sys.exit(1)

        if not isinstance(config["ocr"]["languages"], list):
            print("ERROR: ocr.languages must be a list", file=sys.stderr)
            sys.exit(1)

        if not config["ocr"]["languages"]:
            print("ERROR: ocr.languages must not be empty", file=sys.stderr)
            sys.exit(1)

        if not (0.0 <= config["ocr"]["det_threshold"] <= 1.0):
            print(f"ERROR: det_threshold {config['ocr']['det_threshold']} out of range", file=sys.stderr)
            sys.exit(1)

        if not (0.0 <= config["ocr"]["rec_threshold"] <= 1.0):
            print(f"ERROR: rec_threshold {config['ocr']['rec_threshold']} out of range", file=sys.stderr)
            sys.exit(1)

        if args.validate_only:
            print("✓ Config validation successful", file=sys.stderr)
            return

        # Write JSON output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        print(f"✓ Config rendered to {output_path}", file=sys.stderr)

    except FileNotFoundError:
        print(f"ERROR: Config file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
