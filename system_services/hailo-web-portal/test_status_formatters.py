import unittest

from status_formatters import create_temperature_gauge_html


class StatusFormatterTests(unittest.TestCase):
    def test_temperature_gauge_handles_unavailable_device_temperature(self) -> None:
        html = create_temperature_gauge_html(None)

        self.assertIn("N/A", html)
        self.assertIn("Device status unavailable", html)


if __name__ == "__main__":
    unittest.main()
