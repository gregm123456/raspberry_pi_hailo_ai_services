"""
pytest configuration for hailo-pose tests
"""

import pytest


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--service-url",
        action="store",
        default="http://localhost:11436",
        help="Base URL for hailo-pose service"
    )


@pytest.fixture(scope="session")
def service_url(request):
    """Get service URL from command line or use default."""
    return request.config.getoption("--service-url")
