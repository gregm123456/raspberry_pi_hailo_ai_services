from __future__ import annotations

import asyncio
import os
import re
import subprocess
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
        self._last_good_monitor: Optional[Dict[str, Any]] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def _parse_hailort_monitor_output(output: str) -> Optional[Dict[str, Any]]:
        """Parse single-snapshot output from `hailortcli monitor`."""
        pattern = re.compile(
            r"^\s*(\S+)\s+"  # device id
            r"(\S+)\s+"       # architecture
            r"([\d.]+)\s+"    # nnc util
            r"([\d.]+)\s+"    # cpu util
            r"([\d.]+)\s+"    # ram util
            r"(\d+)\s*/\s*(\d+)\s+"  # used/total MB
            r"([\d.]+)\s+"    # temperature
            r"(\d+)\s*$"      # voltage
        )
        for line in output.splitlines():
            match = pattern.match(line)
            if not match:
                continue

            (
                device_id,
                architecture,
                nnc_util,
                cpu_util,
                ram_util,
                used_mb,
                total_mb,
                temp_c,
                voltage_mv,
            ) = match.groups()

            used_val = float(used_mb)
            total_val = float(total_mb)
            return {
                "device_id": device_id,
                "architecture": architecture,
                "performance": {
                    "nnc_utilization_percent": float(nnc_util),
                    "cpu_utilization_percent": float(cpu_util),
                },
                "ram": {
                    "utilization_percent": float(ram_util),
                    "used_mb": used_val,
                    "total_mb": total_val,
                    "free_mb": max(total_val - used_val, 0.0),
                },
                "thermal": {
                    "temperature_celsius": float(temp_c),
                    "voltage_mv": int(voltage_mv),
                },
                "source": "hailortcli monitor",
            }
        return None

    @staticmethod
    def _read_hailort_monitor_snapshot() -> Dict[str, Any]:
        """Run `hailortcli monitor` and return parsed monitor metrics."""
        try:
            result = subprocess.run(
                ["timeout", "2s", "hailortcli", "monitor"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

        parsed = DeviceStatusMonitor._parse_hailort_monitor_output(result.stdout)
        if parsed:
            parsed["status"] = "ok"
            return parsed

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return {
                "status": "error",
                "message": stderr or f"hailortcli monitor exited with {result.returncode}",
            }
        return {
            "status": "error",
            "message": "Unable to parse hailortcli monitor output",
        }

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
        # Keep RAM monitor data sticky for UI consumers.
        if "monitor" not in self.latest_status and self._last_good_monitor is not None:
            fallback = dict(self._last_good_monitor)
            fallback["stale"] = True
            fallback.setdefault("stale_reason", "monitor data reused")
            combined = dict(self.latest_status)
            combined["monitor"] = fallback
            return combined
        return dict(self.latest_status)

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.status_url, timeout=5) as resp:
                        if resp.status == 200:
                            new_status = await resp.json()

                            monitor_data = await asyncio.to_thread(
                                self._read_hailort_monitor_snapshot
                            )
                            if monitor_data.get("status") == "ok":
                                self._last_good_monitor = monitor_data
                                new_status["monitor"] = monitor_data
                            elif self._last_good_monitor is not None:
                                fallback = dict(self._last_good_monitor)
                                fallback["stale"] = True
                                fallback["stale_reason"] = monitor_data.get("message")
                                new_status["monitor"] = fallback
                            else:
                                new_status["monitor"] = monitor_data

                            # Publish once, so readers never observe an
                            # intermediate payload without monitor data.
                            self.latest_status = new_status
                        else:
                            new_status = {
                                "status": "error",
                                "message": f"status={resp.status}",
                            }
                            if self._last_good_monitor is not None:
                                fallback = dict(self._last_good_monitor)
                                fallback["stale"] = True
                                fallback["stale_reason"] = f"status={resp.status}"
                                new_status["monitor"] = fallback
                            self.latest_status = new_status
            except Exception as exc:  # pragma: no cover - network errors vary
                new_status = {"status": "error", "message": str(exc)}
                if self._last_good_monitor is not None:
                    fallback = dict(self._last_good_monitor)
                    fallback["stale"] = True
                    fallback["stale_reason"] = str(exc)
                    new_status["monitor"] = fallback
                self.latest_status = new_status

            await asyncio.sleep(self.interval_seconds)
