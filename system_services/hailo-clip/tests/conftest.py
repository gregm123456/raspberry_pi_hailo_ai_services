"""
Pytest configuration for hailo-clip service tests.
"""

import pytest


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "service: mark test as requiring hailo-clip service"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test items."""
    for item in items:
        # Mark all tests as service tests
        item.add_marker(pytest.mark.service)
