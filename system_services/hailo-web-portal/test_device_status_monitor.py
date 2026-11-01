import asyncio
import unittest
from unittest.mock import patch

from device_status_monitor import DeviceStatusMonitor


class FakeResponse:
    status = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    async def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, payload: dict) -> None:
        self.response = FakeResponse(payload)

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def get(self, url: str, timeout: int) -> FakeResponse:
        return self.response


class DeviceStatusMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_polls_device_manager_without_opening_a_direct_device_monitor(self):
        manager_status = {
            "status": "ok",
            "device": {
                "architecture": "HAILO10H",
                "temperature_celsius": 44.0,
            },
            "networks": {"networks": []},
        }
        monitor = DeviceStatusMonitor(interval_seconds=0.01)
        monitor._running = True

        with patch(
            "device_status_monitor.aiohttp.ClientSession",
            return_value=FakeSession(manager_status),
        ):
            poll_task = asyncio.create_task(monitor._poll_loop())
            for _ in range(10):
                if monitor.get_status() != {"status": "unknown"}:
                    break
                await asyncio.sleep(0.01)
            monitor._running = False
            await asyncio.wait_for(poll_task, timeout=1)

        self.assertEqual(monitor.get_status(), manager_status)


if __name__ == "__main__":
    unittest.main()
