import aiohttp
import pytest


async def _is_available(url: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=2) as resp:
                return resp.status < 500
    except Exception:
        return False


@pytest.mark.asyncio
async def test_device_status_endpoint() -> None:
    if not await _is_available("http://127.0.0.1:7860/api/status"):
        pytest.skip("Portal not running")

    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:7860/api/status", timeout=5) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_service_status_endpoint() -> None:
    if not await _is_available("http://127.0.0.1:7860/api/services/status"):
        pytest.skip("Portal not running")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://127.0.0.1:7860/api/services/status", timeout=5
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "hailo-ollama" in data
