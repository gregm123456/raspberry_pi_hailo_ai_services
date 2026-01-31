# Hailo Whisper Troubleshooting Guide

Common issues and solutions for hailo-whisper service.

## Service Won't Start

### Symptom
```bash
$ sudo systemctl start hailo-whisper
Job for hailo-whisper.service failed because the control process exited with error code.
```

### Check Logs
```bash
sudo journalctl -u hailo-whisper -n 100 --no-pager
```

### Common Causes

#### 1. Missing Python Dependencies

**Error:**
```
ImportError: No module named 'aiohttp'
```

**Solution:**
```bash
pip3 install aiohttp pyyaml
```

#### 2. Hailo Device Not Found

**Error:**
```
/dev/hailo0 not found
```

**Solution:**
```bash
# Install Hailo driver
sudo apt update
sudo apt install dkms hailo-h10-all
sudo reboot

# Verify device
ls -l /dev/hailo0
hailortcli fw-control identify
```

#### 3. HailoRT Not Installed

**Error:**
```
ImportError: No module named 'hailo_platform'
```

**Solution:**
```bash
# Install HailoRT Python bindings
pip3 install hailort

# Or from Hailo Developer Zone Debian package
# Download from: https://hailo.ai/developer-zone/
sudo dpkg -i hailort-*.deb
```

#### 4. Permission Denied on Hailo Device

**Error:**
```
PermissionError: [Errno 13] Permission denied: '/dev/hailo0'
```

**Solution:**
```bash
# Check device permissions
ls -l /dev/hailo0

# Add service user to hailo group
sudo usermod -aG hailo hailo-whisper

# Restart service
sudo systemctl restart hailo-whisper
```

#### 5. Port Already in Use

**Error:**
```
OSError: [Errno 98] Address already in use
```

**Solution:**
```bash
# Check what's using the port
sudo ss -ltnp | grep 11436

# Kill conflicting process or change port
sudo nano /etc/hailo/hailo-whisper.yaml
# Change port, then:
sudo python3 /usr/lib/hailo-whisper/render_config.py \
  --input /etc/hailo/hailo-whisper.yaml \
  --output /etc/xdg/hailo-whisper/hailo-whisper.json
sudo systemctl restart hailo-whisper
```

---

## Health Check Fails

### Symptom
```bash
$ curl http://localhost:11436/health
curl: (7) Failed to connect to localhost port 11436: Connection refused
```

### Diagnosis

#### 1. Service Not Running
```bash
systemctl status hailo-whisper
```

If inactive, check logs:
```bash
sudo journalctl -u hailo-whisper -n 50 --no-pager
```

#### 2. Wrong Port
Check configured port:
```bash
grep port /etc/hailo/hailo-whisper.yaml
```

Try health check on correct port:
```bash
curl http://localhost:<port>/health
```

#### 3. Firewall Blocking
```bash
# Check firewall rules
sudo iptables -L -n | grep 11436

# If needed, allow port
sudo iptables -A INPUT -p tcp --dport 11436 -j ACCEPT
```

---

## Transcription Fails

### Symptom
```bash
$ curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@audio.mp3" \
  -F model="whisper-small"
{"error": {"message": "...", "type": "internal_error"}}
```

### Common Causes

#### 1. Audio File Too Large

**Error:**
```json
{"error": {"message": "Audio file too large (max 26214400 bytes)", "type": "invalid_request_error"}}
```

**Solution:**
- Compress audio file (reduce bitrate, sample rate)
- Split long audio into chunks
- Increase limit in config (not recommended for stability):
  ```yaml
  transcription:
    max_audio_duration_seconds: 600  # 10 minutes
  ```

#### 2. Unsupported Audio Format

**Error:**
```json
{"error": {"message": "Failed to process audio file", "type": "invalid_request_error"}}
```

**Solution:**
- Convert to supported format (wav, mp3, ogg, flac, webm)
- Use ffmpeg:
  ```bash
  ffmpeg -i input.avi -vn -acodec mp3 output.mp3
  ```

#### 3. Model Not Loaded

**Error:**
```json
{"error": {"message": "Model not loaded", "type": "internal_error"}}
```

**Solution:**
```bash
# Check readiness
curl http://localhost:11436/health/ready

# Check logs for model loading errors
sudo journalctl -u hailo-whisper -n 100 --no-pager | grep -i model

# Restart service
sudo systemctl restart hailo-whisper
```

#### 4. Out of Memory

**Error (in logs):**
```
MemoryError: Cannot allocate memory
```

**Solution:**
```bash
# Check current memory usage
free -h

# Adjust systemd memory limit
sudo nano /etc/systemd/system/hailo-whisper.service
# Increase MemoryMax (if available RAM permits)
MemoryMax=4G

sudo systemctl daemon-reload
sudo systemctl restart hailo-whisper

# Or switch to smaller model
sudo nano /etc/hailo/hailo-whisper.yaml
# Change:
model:
  name: "whisper-base"  # Instead of whisper-small
```

---

## Performance Issues

### Slow Transcription

#### Check NPU Utilization
```bash
# Monitor NPU during transcription
watch -n 1 'cat /sys/class/hailo/hailo0/device/power/runtime_status'
```

#### Check CPU Usage
```bash
top -p $(pgrep -f hailo-whisper)
```

#### Optimization Tips

1. **Use Persistent Model Loading**
   ```yaml
   model:
     keep_alive: -1  # Never unload
   ```

2. **Enable VAD Filtering**
   ```yaml
   transcription:
     vad_filter: true  # Skip silence
   ```

3. **Reduce Beam Size** (faster, slightly less accurate)
   ```yaml
   transcription:
     beam_size: 1  # Greedy decoding
   ```

4. **Switch to Smaller Model**
   ```yaml
   model:
     name: "whisper-base"  # Faster than whisper-small
   ```

---

## Configuration Issues

### Config Changes Not Applied

**Problem:** Modified `/etc/hailo/hailo-whisper.yaml` but service behavior unchanged.

**Solution:**
```bash
# Re-render JSON config
sudo python3 /usr/lib/hailo-whisper/render_config.py \
  --input /etc/hailo/hailo-whisper.yaml \
  --output /etc/xdg/hailo-whisper/hailo-whisper.json

# Restart service
sudo systemctl restart hailo-whisper

# Verify config loaded
curl http://localhost:11436/health
```

### Invalid YAML Syntax

**Error (in logs):**
```
Error: Failed to parse YAML: ...
```

**Solution:**
```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('/etc/hailo/hailo-whisper.yaml'))"

# Fix syntax errors, then re-render
sudo python3 /usr/lib/hailo-whisper/render_config.py \
  --input /etc/hailo/hailo-whisper.yaml \
  --output /etc/xdg/hailo-whisper/hailo-whisper.json
```

---

## Integration Issues

### OpenAI SDK Connection Fails

**Problem:**
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:11436/v1")
# openai.APIConnectionError: Connection error
```

**Solution:**
```bash
# Verify service is running
curl http://localhost:11436/health

# Check firewall (if accessing from another machine)
sudo ufw allow 11436/tcp

# Ensure correct base_url (note /v1 suffix)
client = OpenAI(
    api_key="not-needed",
    base_url="http://localhost:11436/v1"
)
```

### CORS Errors (Browser)

**Problem:** Browser console shows CORS policy error.

**Solution:** Add reverse proxy with CORS headers (nginx example):
```nginx
location / {
    proxy_pass http://localhost:11436;
    add_header Access-Control-Allow-Origin *;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
    add_header Access-Control-Allow-Headers "Content-Type";
}
```

---

## Diagnostic Commands

### Service Status
```bash
systemctl status hailo-whisper
```

### Recent Logs
```bash
sudo journalctl -u hailo-whisper -n 100 --no-pager
```

### Follow Logs (Real-Time)
```bash
sudo journalctl -u hailo-whisper -f
```

### Check Configuration
```bash
cat /etc/hailo/hailo-whisper.yaml
cat /etc/xdg/hailo-whisper/hailo-whisper.json
```

### Test Health
```bash
curl http://localhost:11436/health
curl http://localhost:11436/health/ready
```

### List Models
```bash
curl http://localhost:11436/v1/models
```

### Test Transcription
```bash
# Generate test audio
ffmpeg -f lavfi -i "sine=frequency=1000:duration=2" test.wav

# Transcribe
curl -X POST http://localhost:11436/v1/audio/transcriptions \
  -F file="@test.wav" \
  -F model="whisper-small"
```

### Check System Resources
```bash
# Memory
free -h

# CPU
top -p $(pgrep -f hailo-whisper)

# Disk space
df -h /var/lib/hailo-whisper

# Hailo device
ls -l /dev/hailo0
hailortcli fw-control identify
```

---

## Getting Help

If issues persist:

1. **Collect Diagnostic Information:**
   ```bash
   # Save to file
   {
     echo "=== System Info ==="
     uname -a
     cat /etc/os-release
     echo ""
     echo "=== Service Status ==="
     systemctl status hailo-whisper
     echo ""
     echo "=== Recent Logs ==="
     sudo journalctl -u hailo-whisper -n 100 --no-pager
     echo ""
     echo "=== Configuration ==="
     cat /etc/hailo/hailo-whisper.yaml
     echo ""
     echo "=== Hailo Device ==="
     ls -l /dev/hailo0
     hailortcli fw-control identify
   } > hailo-whisper-diagnostics.txt
   ```

2. **Check Documentation:**
   - [README.md](README.md) - Installation and usage
   - [API_SPEC.md](API_SPEC.md) - API reference
   - [ARCHITECTURE.md](ARCHITECTURE.md) - Design details

3. **Review Logs:** Most issues are logged with clear error messages

4. **GitHub Issues:** Report bugs with diagnostic information

---

## Known Limitations

- **Max Audio Duration:** 300 seconds (5 minutes) by default
- **Max File Size:** 25 MB
- **Concurrent Requests:** Limited by NPU and CPU capacity
- **Language Detection:** Auto-detection may be inaccurate for short clips
- **Real-Time Support:** No streaming/WebSocket support (yet)

---

## Clean Reinstall

If all else fails:

```bash
# Uninstall
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-whisper
sudo ./uninstall.sh

# Clean state
sudo rm -rf /var/lib/hailo-whisper
sudo rm -f /etc/hailo/hailo-whisper.yaml
sudo rm -rf /etc/xdg/hailo-whisper

# Reinstall
sudo ./install.sh --warmup-model
```
