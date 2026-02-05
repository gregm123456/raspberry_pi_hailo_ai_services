#!/usr/bin/env python3
"""
Device manager concurrency test.

This script requires a running hailo-device-manager service.
Optional inference test needs:
  - HAILO_TEST_MODEL_PATH
  - HAILO_TEST_MODEL_TYPE
  - HAILO_TEST_INPUT_JSON (path to JSON containing input_data)

Example:
  export HAILO_TEST_MODEL_PATH=/var/lib/hailo-vision/resources/models/hailo10h/qwen2-vl-2b-instruct.hef
  export HAILO_TEST_MODEL_TYPE=vlm_chat
  export HAILO_TEST_INPUT_JSON=/tmp/vlm_chat_input.json
  python3 test_device_manager_concurrency.py
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict

from device_client import HailoDeviceClient


def load_input_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


async def run_ping(client_id: str) -> None:
    async with HailoDeviceClient() as client:
        response = await client.ping()
        print(f"[{client_id}] ping ok: uptime={response.get('uptime_seconds'):.2f}s")


async def run_infer(client_id: str, model_path: str, model_type: str, input_data: Dict[str, Any]) -> None:
    async with HailoDeviceClient() as client:
        response = await client.infer(model_path, input_data, model_type=model_type)
        print(
            f"[{client_id}] infer ok: inference_time_ms={response.get('inference_time_ms')}"
        )


async def main() -> None:
    await asyncio.gather(run_ping("client-a"), run_ping("client-b"))

    model_path = os.environ.get("HAILO_TEST_MODEL_PATH")
    model_type = os.environ.get("HAILO_TEST_MODEL_TYPE")
    input_json = os.environ.get("HAILO_TEST_INPUT_JSON")

    if not model_path or not model_type or not input_json:
        print("Skipping inference test (set HAILO_TEST_MODEL_PATH, HAILO_TEST_MODEL_TYPE, HAILO_TEST_INPUT_JSON)")
        return

    input_data = load_input_json(input_json)

    await asyncio.gather(
        run_infer("client-a", model_path, model_type, input_data),
        run_infer("client-b", model_path, model_type, input_data),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
