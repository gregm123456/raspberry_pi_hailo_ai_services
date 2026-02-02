# Hailo Vision Service

Deploys Qwen VLM (Qwen2-VL-2B-Instruct) as a systemd service on Raspberry Pi 5 with Hailo-10H, exposing a chat-based vision API on port 11435 with OpenAI-compatible endpoints.

## Prerequisites

- **Hardware**: Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU)
- **OS**: 64-bit Raspberry Pi OS (Bookworm or newer)
- **Drivers**: Hailo-10H kernel driver installed:
  ```bash
  sudo apt install dkms hailo-h10-all
  sudo reboot
  hailortcli fw-control identify  # Verify installation
  ```
- **Dependencies**: Python 3 and basic build tools (installed automatically by `install.sh`)

## Deployment Strategy

To ensure a robust and isolated deployment, this service uses a **vendoring approach**:
- The `hailo-apps` core library is vendored into `/opt/hailo-vision/vendor/` during installation.
- This avoids version conflicts and ensures the `hailo-vision` system user has all necessary permissions and code access without relying on the developer's home directory.
- A dedicated Python virtual environment is created at `/opt/hailo-vision/venv` with access to system-site-packages (for HailoRT bindings).

## Fresh Installation Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/gregm123456/raspberry_pi_hailo_ai_services.git
   cd raspberry_pi_hailo_ai_services/system_services/hailo-vision
   ```

2. **Run the Installer**:
   The installer creates the service user, vendors dependencies, sets up the venv, and installs the systemd unit.
   ```bash
   sudo ./install.sh
   ```

3. **Verify Startup**:
   The service takes ~60 seconds to load the 2B-parameter model onto the NPU.
   ```bash
   # Watch logs for "Service ready"
   sudo journalctl -u hailo-vision.service -f
   ```

4. **Test the API**:
   ```bash
   curl http://localhost:11435/health
   ```

## Configuration

Edit the operator-facing YAML at `/etc/hailo/hailo-vision.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 11435

model:
  name: "qwen2-vl-2b-instruct"
  # keep_alive: -1  # -1 = persistent (default)

generation:
  temperature: 0.7
  max_tokens: 200
```

Apply changes by restarting the service: `sudo systemctl restart hailo-vision`.

## Feature Usage & OpenAI Compatibility

### Vision Querying
The service implements the OpenAI `/v1/chat/completions` endpoint. This allows using official OpenAI SDKs or `curl` to send multimodal prompts.

**Supported Content Types:**
- `text`: Standard text prompts.
- `image_url`: Standard OpenAI format for base64 data URIs or external links.
- `image` (Bundled): A proprietary convenience field for sending raw base64 data without the data URI prefix.

### Client Example (Python OpenAI SDK)
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:11435/v1", api_key="hailo")

response = client.chat.completions.create(
    model="qwen2-vl-2b-instruct",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        ]
    }]
)
print(response.choices[0].message.content)
```

### Batch Analysis
The service also provides a high-level `POST /v1/vision/analyze` endpoint for processing multiple images in a single request with a shared prompt.

## Resource Management
- **Models**: Pre-compiled HEFs are auto-downloaded to `/var/lib/hailo-vision/resources`.
- **NPU Memory**: The model consumes ~3-4GB of Hailo-10H memory.
- **CPU Isolation**: The service is bounded by systemd slices to prevent stealing resources from the main OS tasks.

## Maintenance logs
- **Logs**: `sudo journalctl -u hailo-vision.service -f`
- **Clean Uninstall**: `sudo ./uninstall.sh --purge-data`

