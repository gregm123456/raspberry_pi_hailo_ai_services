"""
Pytest configuration for hailo-depth tests.
"""

import pytest


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--base-url",
        action="store",
        default="http://localhost:11436",
        help="Base URL for hailo-depth service"
    )
    parser.addoption(
        "--timeout",
        action="store",
        type=int,
        default=30,
        help="Request timeout in seconds"
    )


@pytest.fixture(scope="session")
def base_url(request):
    """Get base URL from command line."""
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def timeout(request):
    """Get timeout from command line."""
    return request.config.getoption("--timeout")
