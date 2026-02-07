#!/usr/bin/env python3
"""
Tests for Hailo Device Status Utility

Validates:
- Device enumeration via HailoRT API
- Error handling when device unavailable
- Output formatting (JSON and human-readable)
- CLI command execution
"""

import json
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO
from click.testing import CliRunner

# Import the CLI module
import hailo_device_status


class TestDeviceInfo(unittest.TestCase):
    """Test device info retrieval."""
    
    def setUp(self):
        """Set up common mocks."""
        # Mock board info
        self.mock_board_info = MagicMock()
        self.mock_board_info.device_architecture = "HAILO10H"
        self.mock_board_info.firmware_version = "5.1.1 (release,app)"
        
        # Mock temperature
        self.mock_temp_info = MagicMock()
        self.mock_temp_info.ts0_temperature = 45.3
        
        # Mock control
        self.mock_control = MagicMock()
        self.mock_control.identify.return_value = self.mock_board_info
        self.mock_control.get_chip_temperature.return_value = self.mock_temp_info
        
        # Mock device
        self.mock_device = MagicMock()
        self.mock_device.device_id = "0001:01:00.0"
        self.mock_device.control = self.mock_control
        self.mock_device.loaded_network_groups = []
        self.mock_device.release = MagicMock()
    
    def test_get_device_info_success(self):
        """Test successful device enumeration."""
        with patch('hailo_device_status.Device') as MockDevice:
            MockDevice.scan.return_value = ["0001:01:00.0"]
            MockDevice.return_value = self.mock_device
            result = hailo_device_status.get_device_info()
        
        # Verify structure
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["device_count"], 1)
        self.assertEqual(len(result["devices"]), 1)
        
        # Verify device data
        device = result["devices"][0]
        self.assertEqual(device["device_id"], "0001:01:00.0")
        self.assertEqual(device["architecture"], "HAILO10H")
        self.assertEqual(device["fw_version"], "5.1.1 (release,app)")
        self.assertEqual(device["temperature_celsius"], 45.3)
    
    def test_get_device_info_no_devices(self):
        """Test when no devices detected."""
        with patch('hailo_device_status.Device') as MockDevice:
            MockDevice.scan.return_value = []
            result = hailo_device_status.get_device_info()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["device_count"], 0)
        self.assertIn("No Hailo devices", result["message"])
    
    def test_get_device_info_temperature_unavailable(self):
        """Test graceful handling of missing temperature."""
        # Mock control - temperature fails
        mock_control = MagicMock()
        mock_control.identify.return_value = self.mock_board_info
        mock_control.get_chip_temperature.side_effect = RuntimeError("Sensor not available")
        
        # Mock device
        mock_device = MagicMock()
        mock_device.device_id = "0001:01:00.0"
        mock_device.control = mock_control
        mock_device.loaded_network_groups = []
        mock_device.release = MagicMock()
        
        with patch('hailo_device_status.Device') as MockDevice:
            MockDevice.scan.return_value = ["0001:01:00.0"]
            MockDevice.return_value = mock_device
            result = hailo_device_status.get_device_info()
        
        # Should still return ok status
        self.assertEqual(result["status"], "ok")
        device = result["devices"][0]
        self.assertIsNone(device["temperature_celsius"])
        self.assertIn("Sensor not available", device["temperature_error"])
    
    def test_get_device_info_api_error(self):
        """Test error handling for API failures."""
        with patch('hailo_device_status.Device') as MockDevice:
            MockDevice.scan.side_effect = RuntimeError("Device enumeration failed")
            result = hailo_device_status.get_device_info()
        
        self.assertEqual(result["status"], "error")
        self.assertIn("Device enumeration failed", result["message"])


class TestNetworksInfo(unittest.TestCase):
    """Test loaded networks retrieval."""
    
    def test_get_loaded_networks_vdevice_available(self):
        """Test networks retrieval with VDevice available."""
        # Mock network group
        mock_input_layer = MagicMock()
        mock_output_layer = MagicMock()
        mock_network_group = MagicMock()
        mock_network_group.name = "yolo_detection"
        mock_network_group.input_layers = [mock_input_layer]
        mock_network_group.output_layers = [mock_output_layer, mock_output_layer]
        
        mock_vdevice = MagicMock()
        mock_vdevice.get_network_groups.return_value = [mock_network_group]
        
        with patch('hailo_device_status.Device') as MockDevice:
            with patch('hailo_device_status.VDevice', return_value=mock_vdevice):
                MockDevice.scan.return_value = ["0001:01:00.0"]
                result = hailo_device_status.get_loaded_networks()
        
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["network_count"], 1)
        self.assertEqual(result["networks"][0]["name"], "yolo_detection")
        self.assertEqual(result["networks"][0]["input_count"], 1)
        self.assertEqual(result["networks"][0]["output_count"], 2)
    
    def test_get_loaded_networks_vdevice_unavailable(self):
        """Test fallback to device API when VDevice unavailable."""
        # Mock network group from device
        mock_network_group = MagicMock()
        mock_network_group.name = "detection_net"
        mock_network_group.input_layers = [MagicMock()]
        mock_network_group.output_layers = [MagicMock()]
        
        # Mock device
        mock_device = MagicMock()
        mock_device.loaded_network_groups = [mock_network_group]
        mock_device.release = MagicMock()
        
        # VDevice fails, Device succeeds
        with patch('hailo_device_status.Device') as MockDevice:
            with patch('hailo_device_status.VDevice', side_effect=RuntimeError("VDevice not available")):
                MockDevice.scan.return_value = ["0001:01:00.0"]
                MockDevice.return_value = mock_device
                result = hailo_device_status.get_loaded_networks()
        
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["network_count"], 1)
        self.assertEqual(result["networks"][0]["name"], "detection_net")
        self.assertEqual(result["source"], "Device (direct access)")
    
    def test_get_loaded_networks_both_unavailable(self):
        """Test graceful handling when both VDevice and Device unavailable."""
        # Both APIs fail
        with patch('hailo_device_status.Device') as MockDevice:
            with patch('hailo_device_status.VDevice', side_effect=RuntimeError("VDevice not available")):
                MockDevice.scan.side_effect = RuntimeError("Device scan failed")
                result = hailo_device_status.get_loaded_networks()
        
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["network_count"], 0)
        self.assertEqual(len(result["networks"]), 0)
    
    def test_get_loaded_networks_no_networks(self):
        """Test when device available but no networks loaded."""
        mock_device = MagicMock()
        mock_device.loaded_network_groups = []
        mock_device.release = MagicMock()
        
        with patch('hailo_device_status.Device') as MockDevice:
            with patch('hailo_device_status.VDevice', side_effect=RuntimeError("VDevice not available")):
                MockDevice.scan.return_value = ["0001:01:00.0"]
                MockDevice.return_value = mock_device
                result = hailo_device_status.get_loaded_networks()
        
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["network_count"], 0)


class TestFormatting(unittest.TestCase):
    """Test output formatting."""
    
    def test_format_device_output_json(self):
        """Test JSON formatting of device output."""
        device_data = {
            "status": "ok",
            "device_count": 1,
            "devices": [{
                "index": 0,
                "device_id": "0000:04:00.0",
                "architecture": "HAILO_ARCH_H10_A",
                "fw_version": "4.28.8",
                "temperature_celsius": 45.3
            }]
        }
        
        output = hailo_device_status.format_device_output(device_data, json_output=True)
        parsed = json.loads(output)
        
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["device_count"], 1)
    
    def test_format_device_output_human_readable(self):
        """Test human-readable formatting."""
        device_data = {
            "status": "ok",
            "device_count": 1,
            "devices": [{
                "index": 0,
                "device_id": "0000:04:00.0",
                "architecture": "HAILO_ARCH_H10_A",
                "fw_version": "4.28.8",
                "temperature_celsius": 45.3
            }]
        }
        
        output = hailo_device_status.format_device_output(device_data, json_output=False)
        
        self.assertIn("Hailo Devices", output)
        self.assertIn("0000:04:00.0", output)
        self.assertIn("4.28.8", output)
        self.assertIn("45.3°C", output)
    
    def test_format_device_output_error(self):
        """Test error formatting."""
        device_data = {
            "status": "error",
            "message": "No Hailo devices detected"
        }
        
        output = hailo_device_status.format_device_output(device_data, json_output=False)
        
        self.assertIn("Error", output)
        self.assertIn("No Hailo devices", output)


class TestCLICommands(unittest.TestCase):
    """Test CLI command execution."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
    
    def test_device_command_format(self):
        """Test that device command outputs expected format."""
        # Test with real device if available, otherwise skip CLI tests
        # The function tests above validate the logic; here we test command structure
        result = self.runner.invoke(hailo_device_status.cli, ['device', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Show device information", result.output)
    
    def test_networks_command_help(self):
        """Test networks command help text."""
        result = self.runner.invoke(hailo_device_status.cli, ['networks', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Show networks loaded by this process", result.output)
    
    def test_status_command_help(self):
        """Test status command help text."""
        result = self.runner.invoke(hailo_device_status.cli, ['status', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Show complete device status", result.output)
    
    def test_health_command_help(self):
        """Test health command help text."""
        result = self.runner.invoke(hailo_device_status.cli, ['health', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("health check", result.output)
    
    def test_json_flag_availability(self):
        """Test that --json flag is available on device command."""
        result = self.runner.invoke(hailo_device_status.cli, ['device', '--help'])
        self.assertIn("--json", result.output)


if __name__ == "__main__":
    unittest.main()
