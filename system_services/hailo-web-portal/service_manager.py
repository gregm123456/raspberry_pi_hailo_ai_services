from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import subprocess
from typing import Dict, List

import aiohttp

logger = logging.getLogger(__name__)

DEVICE_SOCKET = os.getenv("HAILO_DEVICE_SOCKET", "/run/hailo/device.sock")
DEVICE_STATUS_URL = os.getenv(
    "HAILO_DEVICE_STATUS_URL", "http://127.0.0.1:5099/v1/device/status"
)


class ServiceManager:
    SERVICE_NAMES = [
        "hailo-device-manager",
        "hailo-ollama",
        "hailo-vision",
        "hailo-whisper",
        "hailo-audio",
        "hailo-face",
        "hailo-super-resolution",
        "hailo-ocr",
        "hailo-clip",
        "hailo-pose",
        "hailo-depth",
        "hailo-tracking",
        "hailo-piper",
    ]

    OLLAMA_CONFLICTS = [
        "hailo-vision",
        "hailo-whisper",
        "hailo-audio",
        "hailo-face",
        "hailo-super-resolution",
        "hailo-ocr",
        "hailo-clip",
        "hailo-pose",
        "hailo-depth",
        "hailo-tracking",
        "hailo-piper",
    ]

    async def get_status(self) -> Dict[str, str]:
        results = await asyncio.gather(
            *[self._is_active(service) for service in self.SERVICE_NAMES]
        )
        return {service: status for service, status in results}

    async def get_startup_status(self) -> Dict[str, str]:
        results = await asyncio.gather(
            *[self._is_enabled(service) for service in self.SERVICE_NAMES]
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
        result = await self._run_systemctl(["stop", service_name])
        if service_name != "hailo-device-manager":
            await self._release_models(service_name)
        return result

    async def _release_models(self, service_name: str) -> None:
        """Unload a stopped service's models from the Device Manager.

        Services don't reliably unload on shutdown, so their models would
        otherwise stay resident (and shown as loaded) until LRU eviction.
        Model files live under /var/lib/<service>/.
        """
        prefix = f"/var/lib/{service_name}/"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(DEVICE_STATUS_URL, timeout=5) as resp:
                    status = await resp.json()
            models = [
                n for n in status.get("networks", {}).get("networks", [])
                if str(n.get("model_path", "")).startswith(prefix)
            ]
            for net in models:
                await self._unload_model(net["model_path"], net.get("model_type", "vlm"))
        except Exception as exc:
            logger.warning("Could not release models for %s: %s", service_name, exc)

    @staticmethod
    async def _unload_model(model_path: str, model_type: str) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(DEVICE_SOCKET), timeout=5
        )
        try:
            body = json.dumps(
                {"action": "unload_model", "model_path": model_path, "model_type": model_type}
            ).encode()
            writer.write(struct.pack(">I", len(body)) + body)
            await writer.drain()
            header = await asyncio.wait_for(reader.readexactly(4), timeout=30)
            await reader.readexactly(struct.unpack(">I", header)[0])
        finally:
            writer.close()

    async def restart_service(self, service_name: str) -> Dict[str, str]:
        return await self._run_systemctl(["restart", service_name])

    async def enable_service(self, service_name: str) -> Dict[str, str]:
        return await self._run_systemctl(["enable", service_name])

    async def disable_service(self, service_name: str) -> Dict[str, str]:
        return await self._run_systemctl(["disable", service_name])

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

    async def _is_enabled(self, service_name: str) -> List[str]:
        result = await asyncio.to_thread(
            subprocess.run,
            ["systemctl", "is-enabled", service_name],
            capture_output=True,
            text=True,
        )
        status = result.stdout.strip() or result.stderr.strip()
        if result.returncode == 0:
            return [service_name, "enabled"]
        if status in {"disabled", "static", "indirect", "masked", "generated"}:
            return [service_name, status]
        return [service_name, "unknown"]

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
