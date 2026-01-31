import os
import shutil
import subprocess
import sys
import urllib.request

import pytest


def _has_command(command: str) -> bool:
    return shutil.which(command) is not None


def _unit_exists() -> bool:
    if not _has_command("systemctl"):
        return False
    result = subprocess.run(
        ["systemctl", "list-unit-files", "hailo-ollama.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "hailo-ollama.service" in result.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
@pytest.mark.skipif(not os.path.exists("/dev/hailo0"), reason="Hailo device missing")
@pytest.mark.skipif(not _has_command("hailo-ollama"), reason="hailo-ollama missing")
@pytest.mark.skipif(not _unit_exists(), reason="systemd unit not installed")
def test_service_active_and_version():
    subprocess.run(
        ["systemctl", "is-active", "--quiet", "hailo-ollama.service"],
        check=True,
    )

    port = os.environ.get("HAILO_OLLAMA_PORT", "11434")
    url = f"http://localhost:{port}/api/version"

    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
