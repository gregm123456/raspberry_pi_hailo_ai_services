import asyncio
import os
import signal
import tempfile
import threading
import time
import unittest
from urllib.request import urlopen
from unittest.mock import Mock, patch

from hailo_device_manager import HailoDeviceManager, ModelEntry


class RuntimeRecoveryTests(unittest.TestCase):
    def make_manager(self) -> HailoDeviceManager:
        manager = HailoDeviceManager()
        manager.device = object()
        manager.vdevice = object()
        manager._ensure_runtime_context = Mock(return_value=None)

        def reset_runtime() -> None:
            manager.loaded_models.clear()
            manager._runtime_broken_reason = None

        manager._reset_runtime_context = Mock(side_effect=reset_runtime)
        return manager

    def test_identifies_fatal_runtime_errors_but_not_capacity_errors(self) -> None:
        for message in (
            "57",
            "HAILO_SHUTDOWN_EVENT_SIGNALED(57)",
            "HAILO_COMMUNICATION_CLOSED(62)",
            "Communication closed failure. Check server-client connection",
        ):
            with self.subTest(message=message):
                self.assertTrue(
                    HailoDeviceManager._is_runtime_context_failure(
                        RuntimeError(message)
                    )
                )

        self.assertFalse(
            HailoDeviceManager._is_runtime_context_failure(
                RuntimeError("HAILO_RESOURCE_EXHAUSTED(81)")
            )
        )

    def test_retries_model_load_once_after_resetting_fatal_context(self) -> None:
        manager = self.make_manager()
        handler = Mock()
        loaded_model = object()
        handler.load.side_effect = [RuntimeError("57"), loaded_model]
        manager._get_handler = Mock(return_value=handler)

        with tempfile.NamedTemporaryFile() as model_file:
            result = manager._load_model(
                {"model_path": model_file.name, "model_type": "test"}
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(handler.load.call_count, 2)
        manager._reset_runtime_context.assert_called_once_with()
        self.assertIs(
            manager.loaded_models[f"test:{model_file.name}"].model,
            loaded_model,
        )

    def test_cleans_context_and_returns_error_after_repeated_fatal_load(self) -> None:
        manager = self.make_manager()
        handler = Mock()
        handler.load.side_effect = RuntimeError("57")
        manager._get_handler = Mock(return_value=handler)

        with tempfile.NamedTemporaryFile() as model_file:
            result = manager._load_model(
                {"model_path": model_file.name, "model_type": "test"}
            )

        self.assertIn("error", result)
        self.assertEqual(handler.load.call_count, 2)
        self.assertEqual(manager._reset_runtime_context.call_count, 2)
        self.assertEqual(manager.loaded_models, {})

    def test_resets_context_after_fatal_inference(self) -> None:
        manager = self.make_manager()
        handler = Mock()
        handler.infer.side_effect = RuntimeError(
            "HAILO_COMMUNICATION_CLOSED(62)"
        )
        manager._get_handler = Mock(return_value=handler)

        with tempfile.NamedTemporaryFile() as model_file:
            key = f"test:{model_file.name}"
            manager.loaded_models[key] = ModelEntry(
                model_type="test",
                model_path=model_file.name,
                model=object(),
                loaded_at=0,
                last_used=0,
            )
            result = manager._infer(
                {
                    "model_path": model_file.name,
                    "model_type": "test",
                    "input_data": {},
                }
            )

        self.assertIn("error", result)
        manager._reset_runtime_context.assert_called_once_with()
        self.assertEqual(manager.loaded_models, {})

    def test_device_status_reports_failed_device_identification(self) -> None:
        manager = self.make_manager()
        device = Mock()
        device.device_id = "pci/0001:01:00.0"
        device.control.identify.side_effect = RuntimeError(
            "Communication closed failure"
        )
        device.control.get_chip_temperature.side_effect = RuntimeError(
            "Communication closed failure"
        )
        manager.device = device

        result = manager._device_status_payload()

        self.assertEqual(result["status"], "error")
        self.assertIn("identify_error", result["device"])

    def test_worker_requests_supervised_restart_after_runtime_reset_failure(self) -> None:
        async def run_test() -> None:
            manager = self.make_manager()
            manager._runtime_broken_reason = "runtime reset failed"
            manager._schedule_restart_for_broken_runtime = Mock()
            manager._handle_request_sync = Mock(return_value={"error": "unavailable"})
            future = asyncio.get_running_loop().create_future()
            manager._request_queue.put_nowait(({"action": "ping"}, future))

            worker = asyncio.create_task(manager._worker_loop())
            try:
                self.assertEqual(await future, {"error": "unavailable"})
                await manager._request_queue.join()
                manager._request_queue.put_nowait(None)
                await worker
                manager._schedule_restart_for_broken_runtime.assert_called_once()
            finally:
                manager._executor.shutdown(wait=True)

        asyncio.run(run_test())

    def test_broken_runtime_schedules_only_one_systemd_restart(self) -> None:
        manager = self.make_manager()
        loop = Mock()

        manager._schedule_restart_for_broken_runtime(loop)
        manager._schedule_restart_for_broken_runtime(loop)

        self.assertEqual(loop.call_later.call_count, 2)
        graceful_restart = loop.call_later.call_args_list[0].args
        self.assertEqual(graceful_restart[0], 0.5)
        self.assertIs(graceful_restart[1], os.kill)
        self.assertEqual(graceful_restart[2], os.getpid())
        self.assertEqual(graceful_restart[3], signal.SIGTERM)
        forced_restart = loop.call_later.call_args_list[1].args
        self.assertEqual(forced_restart[0], 5.0)
        self.assertEqual(
            forced_restart[1].__name__, "_force_kill_after_restart_timeout"
        )

    def test_force_kill_escalation_uses_sigkill_for_supervised_restart(self) -> None:
        manager = self.make_manager()

        with patch("hailo_device_manager.os.kill") as send_signal:
            manager._force_kill_after_restart_timeout()

        send_signal.assert_called_once_with(os.getpid(), signal.SIGKILL)

    def test_status_server_shutdown_does_not_wait_for_active_handler(self) -> None:
        manager = self.make_manager()
        manager.http_bind = ("127.0.0.1", 0)
        handler_entered = threading.Event()
        release_handler = threading.Event()

        def blocked_status() -> dict:
            handler_entered.set()
            release_handler.wait(timeout=5)
            return {"status": "ok"}

        manager._device_status_payload = blocked_status
        manager._start_http_server()
        self.assertIsNotNone(manager._http_server)
        port = manager._http_server.server_address[1]
        request = threading.Thread(
            target=lambda: urlopen(f"http://127.0.0.1:{port}/v1/device/status", timeout=5).read()
        )
        request.start()

        try:
            self.assertTrue(handler_entered.wait(timeout=2))
            shutdown_started = time.monotonic()
            manager._stop_http_server()
            self.assertLess(time.monotonic() - shutdown_started, 2)
            self.assertFalse(manager._http_thread)
        finally:
            release_handler.set()
            request.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
