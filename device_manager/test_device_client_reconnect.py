import unittest
from unittest.mock import AsyncMock, patch

from device_client import HailoDeviceClient


class FakeWriter:
    def __init__(self) -> None:
        self.closed = False

    def is_closing(self) -> bool:
        return self.closed

    def write(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


class DeviceClientReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_once_after_stale_socket_disconnect(self) -> None:
        client = HailoDeviceClient(socket_path="/tmp/device.sock")
        first_writer = FakeWriter()
        second_writer = FakeWriter()

        with (
            patch(
                "device_client.asyncio.open_unix_connection",
                new_callable=AsyncMock,
                side_effect=[
                    (object(), first_writer),
                    (object(), second_writer),
                ],
            ) as open_connection,
            patch(
                "device_client._write_message",
                new_callable=AsyncMock,
                side_effect=[ConnectionResetError("Connection lost"), None],
            ) as write_message,
            patch(
                "device_client._read_message",
                new_callable=AsyncMock,
                return_value={"request_id": "test-request", "status": "ok"},
            ) as read_message,
        ):
            result = await client._send_request(
                {"action": "ping", "request_id": "test-request"}
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(open_connection.await_count, 2)
        self.assertEqual(write_message.await_count, 2)
        self.assertEqual(read_message.await_count, 1)
        self.assertTrue(first_writer.closed)
        self.assertIs(client.writer, second_writer)
        await client.disconnect()

    async def test_does_not_retry_device_manager_errors(self) -> None:
        client = HailoDeviceClient(socket_path="/tmp/device.sock")
        writer = FakeWriter()

        with (
            patch(
                "device_client.asyncio.open_unix_connection",
                new_callable=AsyncMock,
                return_value=(object(), writer),
            ) as open_connection,
            patch("device_client._write_message", new_callable=AsyncMock),
            patch(
                "device_client._read_message",
                new_callable=AsyncMock,
                return_value={
                    "request_id": "test-request",
                    "error": "HAILO_RESOURCE_EXHAUSTED",
                },
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Device manager error"):
                await client._send_request(
                    {"action": "infer", "request_id": "test-request"}
                )

        self.assertEqual(open_connection.await_count, 1)
        await client.disconnect()


if __name__ == "__main__":
    unittest.main()
