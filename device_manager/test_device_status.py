#!/usr/bin/env python3
"""
Test the new device_status action in device_manager.
"""

import asyncio
import sys
import os

# Add the device_manager directory to path so we can import device_client
sys.path.insert(0, os.path.dirname(__file__))

from device_client import HailoDeviceClient

async def test_device_status():
    try:
        async with HailoDeviceClient() as client:
            print("Testing device_status...")
            result = await client.device_status()
            print("✓ device_status response:")
            import json
            print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_device_status())