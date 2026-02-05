#!/usr/bin/env python3
"""
Hailo Device Manager Client

Services use this client to communicate with hailo-device-manager daemon
instead of creating their own VDevice connections.

Usage:
    from device_client import HailoDeviceClient

    async with HailoDeviceClient() as client:
        await client.load_model("/path/to/model.hef")
        result = await client.infer("/path/to/model.hef", input_data)

The client handles:
- Unix socket connection lifecycle
- Request/response framing
- Error handling and reporting
"""

import asyncio
import json
import logging
import os
import struct
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


DEFAULT_SOCKET_PATH = "/run/hailo/device.sock"
DEFAULT_MAX_MESSAGE_BYTES = 8 * 1024 * 1024


async def _read_exact(reader: asyncio.StreamReader, size: int) -> Optional[bytes]:
    try:
        return await reader.readexactly(size)
    except asyncio.IncompleteReadError:
        return None


async def _read_message(
    reader: asyncio.StreamReader, max_bytes: int
) -> Optional[Dict[str, Any]]:
    header = await _read_exact(reader, 4)
    if not header:
        return None
    (length,) = struct.unpack(">I", header)
    if length > max_bytes:
        raise RuntimeError(f"Response too large: {length} bytes")
    payload = await _read_exact(reader, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


async def _write_message(
    writer: asyncio.StreamWriter, payload: Dict[str, Any], max_bytes: int
) -> None:
    body = json.dumps(payload).encode("utf-8")
    if len(body) > max_bytes:
        raise RuntimeError(f"Request too large: {len(body)} bytes")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()


class HailoDeviceClient:
    """Client for communicating with hailo-device-manager."""
    
    def __init__(
        self,
        socket_path: Optional[str] = None,
        timeout: float = 30.0,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
    ):
        """
        Initialize client.
        
        Args:
            socket_path: Path to device manager socket.
                        Defaults to HAILO_DEVICE_SOCKET env var or /run/hailo/device.sock
            timeout: Request timeout in seconds
        """
        self.socket_path = socket_path or os.environ.get(
            "HAILO_DEVICE_SOCKET", DEFAULT_SOCKET_PATH
        )
        self.timeout = timeout
        self.max_message_bytes = max_message_bytes
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
    
    async def connect(self):
        """Connect to device manager socket."""
        attempt = 0
        while True:
            attempt += 1
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self.socket_path),
                    timeout=self.timeout,
                )
                logger.debug("Connected to device manager at %s", self.socket_path)
                return
            except FileNotFoundError:
                raise RuntimeError(
                    f"Device manager socket not found at {self.socket_path}"
                )
            except Exception as e:
                if attempt >= 3:
                    raise RuntimeError(f"Failed to connect to device manager: {e}")
                await asyncio.sleep(0.25 * attempt)
    
    async def disconnect(self):
        """Disconnect from device manager."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
                logger.debug("Disconnected from device manager")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self.writer = None
                self.reader = None
    
    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request and get response."""
        async with self._lock:
            if not self.writer:
                await self.connect()

            request_id = request.get("request_id", str(uuid.uuid4()))
            request["request_id"] = request_id

            try:
                await _write_message(self.writer, request, self.max_message_bytes)
                response = await asyncio.wait_for(
                    _read_message(self.reader, self.max_message_bytes),
                    timeout=self.timeout,
                )
                if not response:
                    raise RuntimeError("Device manager connection closed")
            except asyncio.TimeoutError:
                await self.disconnect()
                raise RuntimeError("Request timeout")
            except Exception as e:
                await self.disconnect()
                raise RuntimeError(f"Request failed: {e}")

            if response.get("request_id") != request_id:
                raise RuntimeError("Mismatched response request_id")

            if "error" in response:
                raise RuntimeError(f"Device manager error: {response['error']}")

            return response
    
    async def ping(self) -> Dict[str, Any]:
        """Ping device manager to verify connection."""
        return await self._send_request({"action": "ping"})
    
    async def status(self) -> Dict[str, Any]:
        """Get device manager status."""
        return await self._send_request({"action": "status"})
    
    async def load_model(
        self,
        model_path: str,
        model_type: str = "vlm",
        model_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Load a model into the device.
        
        Args:
            model_path: Path to .hef model file
            
        Returns:
            Response dict with 'status' and 'message'
        """
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        request = {
            "action": "load_model",
            "model_path": str(model_path),
            "model_type": model_type,
        }
        if model_params:
            request["model_params"] = model_params

        return await self._send_request(request)
    
    async def infer(
        self, model_path: str, input_data: Any, model_type: str = "vlm", model_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run inference with a model.
        
        The model will be loaded if not already loaded.
        
        Args:
            model_path: Path to .hef model file
            input_data: Input data for the model (e.g., image, tensor)
            model_type: Type of model (vlm, vlm_chat, clip)
            model_params: Optional parameters for model loading (passed if model not already loaded)
            
        Returns:
            Response dict with 'result' and 'inference_time_ms'
        """
        request = {
            "action": "infer",
            "model_path": str(model_path),
            "model_type": model_type,
            "input_data": input_data,
        }
        if model_params:
            request["model_params"] = model_params
        
        return await self._send_request(request)
    
    async def unload_model(
        self, model_path: str, model_type: str = "vlm"
    ) -> Dict[str, Any]:
        """
        Unload a model from the device.
        
        Args:
            model_path: Path to .hef model file
            
        Returns:
            Response dict with 'status' and 'message'
        """
        return await self._send_request(
            {
                "action": "unload_model",
                "model_path": str(model_path),
                "model_type": model_type,
            }
        )


def create_client(socket_path: Optional[str] = None) -> HailoDeviceClient:
    """
    Create a new device client.
    
    This is a convenience function for synchronous code that needs
    to communicate with the device manager.
    
    Example (sync wrapper):
        client = create_client()
        asyncio.run(client_example(client))
    
    Args:
        socket_path: Optional path to device manager socket
        
    Returns:
        HailoDeviceClient instance
    """
    return HailoDeviceClient(socket_path)


# Example usage
if __name__ == '__main__':
    import sys
    
    async def main():
        try:
            async with HailoDeviceClient() as client:
                # Test connection
                print("Testing connection...")
                pong = await client.ping()
                print(f"✓ Ping: {pong}")
                
                # Get status
                print("\nGetting status...")
                status = await client.status()
                print(f"✓ Status: {status}")
                
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
    
    asyncio.run(main())
