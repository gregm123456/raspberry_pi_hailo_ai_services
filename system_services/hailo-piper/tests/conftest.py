"""
Pytest configuration for hailo-piper service tests.
"""

import pytest
import requests
import time


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--service-url",
        action="store",
        default="http://localhost:5002",
        help="Base URL of the hailo-piper service"
    )
    parser.addoption(
        "--skip-integration",
        action="store_true",
        default=False,
        help="Skip integration tests that require running service"
    )


@pytest.fixture(scope="session")
def service_url(request):
    """Get service URL from command line."""
    return request.config.getoption("--service-url")


@pytest.fixture(scope="session")
def skip_integration(request):
    """Check if integration tests should be skipped."""
    return request.config.getoption("--skip-integration")


@pytest.fixture(scope="session")
def wait_for_service(service_url):
    """Wait for service to be ready before running tests."""
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{service_url}/health", timeout=2)
            if response.status_code == 200:
                print(f"\n✓ Service ready at {service_url}")
                return True
        except requests.exceptions.RequestException:
            if attempt < max_attempts - 1:
                time.sleep(1)
            else:
                pytest.skip(f"Service not available at {service_url}")
    return False


@pytest.fixture
def client(service_url, wait_for_service):
    """HTTP client for testing the service."""
    return requests.Session()
