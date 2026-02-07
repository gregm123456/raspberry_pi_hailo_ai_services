from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

import aiohttp


class DeviceStatusMonitor:
    def __init__(
        self,
        status_url: Optional[str] = None,
        interval_seconds: float = 3.0,
    ) -> None:
        self.status_url = status_url or os.getenv(
            "HAILO_DEVICE_STATUS_URL", "http://127.0.0.1:5099/v1/device/status"
        )
        self.interval_seconds = interval_seconds
        self.latest_status: Dict[str, Any] = {"status": "unknown"}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task

    def get_status(self) -> Dict[str, Any]:
        return self.latest_status

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.status_url, timeout=5) as resp:
                        if resp.status == 200:
                            self.latest_status = await resp.json()
                        else:
                            self.latest_status = {
                                "status": "error",
                                "message": f"status={resp.status}",
                            }
            except Exception as exc:  # pragma: no cover - network errors vary
                self.latest_status = {"status": "error", "message": str(exc)}

            await asyncio.sleep(self.interval_seconds)
