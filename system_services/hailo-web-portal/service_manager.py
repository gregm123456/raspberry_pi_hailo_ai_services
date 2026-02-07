from __future__ import annotations

import asyncio
import subprocess
from typing import Dict, List


class ServiceManager:
    SERVICE_NAMES = [
        "hailo-device-manager",
        "hailo-ollama",
        "hailo-vision",
        "hailo-whisper",
        "hailo-ocr",
        "hailo-clip",
        "hailo-pose",
        "hailo-depth",
        "hailo-piper",
    ]

    OLLAMA_CONFLICTS = [
        "hailo-vision",
        "hailo-whisper",
        "hailo-ocr",
        "hailo-clip",
        "hailo-pose",
        "hailo-depth",
        "hailo-piper",
    ]

    async def get_status(self) -> Dict[str, str]:
        results = await asyncio.gather(
            *[self._is_active(service) for service in self.SERVICE_NAMES]
        )
        return {service: status for service, status in results}

    async def start_service(self, service_name: str) -> Dict[str, str]:
        if service_name == "hailo-ollama":
            conflicts = await self._check_ollama_conflicts()
            if conflicts:
                return {
                    "status": "error",
                    "message": "Cannot start hailo-ollama while other services are running: "
                    + ", ".join(conflicts),
                }

        return await self._run_systemctl(["start", service_name])

    async def stop_service(self, service_name: str) -> Dict[str, str]:
        return await self._run_systemctl(["stop", service_name])

    async def restart_service(self, service_name: str) -> Dict[str, str]:
        return await self._run_systemctl(["restart", service_name])

    async def _is_active(self, service_name: str) -> List[str]:
        result = await asyncio.to_thread(
            subprocess.run,
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return [service_name, "running"]
        if result.stdout.strip() == "inactive":
            return [service_name, "stopped"]
        return [service_name, "error"]

    async def _run_systemctl(self, args: List[str]) -> Dict[str, str]:
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["sudo", "systemctl", *args],
                check=True,
                capture_output=True,
                text=True,
            )
            return {"status": "ok"}
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            return {"status": "error", "message": message}

    async def _check_ollama_conflicts(self) -> List[str]:
        status = await self.get_status()
        return [
            name
            for name in self.OLLAMA_CONFLICTS
            if status.get(name) == "running"
        ]
