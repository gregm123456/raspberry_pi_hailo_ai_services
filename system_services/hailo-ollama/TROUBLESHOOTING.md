# Troubleshooting Hailo Ollama Service

## Service fails to start

**Diagnostic:**
```bash
sudo systemctl status hailo-ollama.service
sudo journalctl -u hailo-ollama.service -n 50 --no-pager
```

**Likely causes:**
- `/dev/hailo0` missing
- `hailo-ollama` binary not installed
- Port already in use

**Fix:**
1. Verify device: `ls -l /dev/hailo0`
2. Verify binary: `command -v hailo-ollama`
3. Change port in `/etc/hailo/hailo-ollama.yaml` and re-run install

## Permission denied on /dev/hailo0

**Diagnostic:**
```bash
ls -l /dev/hailo0
id hailo-ollama
```

**Fix:**
```bash
sudo usermod -aG $(stat -c '%G' /dev/hailo0) hailo-ollama
sudo systemctl restart hailo-ollama.service
```

## Health check fails at /api/version

**Diagnostic:**
```bash
curl -v http://localhost:11434/api/version
sudo journalctl -u hailo-ollama.service -n 100 --no-pager
```

**Fix:**
- Ensure the service is active: `sudo systemctl is-active hailo-ollama.service`
- Check for port conflicts: `ss -lntp | grep 11434`

## Model pull fails

**Diagnostic:**
```bash
curl -X POST http://localhost:11434/api/pull -H "Content-Type: application/json" -d '{"name":"qwen2:1.5b"}'
```

**Likely causes:**
- No internet access
- Remote library unavailable

**Fix:**
- Verify networking: `ping -c 1 8.8.8.8`
- Retry later or change `library.host` in `/etc/hailo/hailo-ollama.yaml`

## High latency on first inference

**Expected:** The first inference after a pull can take 10–30 seconds.

**Fix:**
- Use warmup during install: `sudo ./install.sh --warmup-chat qwen2:1.5b`
- Keep the service running to keep the model resident

## Thermal throttling

**Diagnostic:**
```bash
vcgencmd measure_temp
```

**Fix:**
- Add active cooling or reduce model size
- Reduce CPU quota in the systemd unit

## YAML rendering errors

**Diagnostic:**
```bash
sudo python3 render_config.py --input /etc/hailo/hailo-ollama.yaml --output /etc/xdg/hailo-ollama/hailo-ollama.json
```

**Fix:**
- Install PyYAML: `sudo apt install python3-yaml`
- Correct YAML syntax and re-run installer
