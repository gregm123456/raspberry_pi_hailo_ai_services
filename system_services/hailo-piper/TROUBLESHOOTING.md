# Hailo Piper TTS Troubleshooting

Common issues and solutions for the Hailo Piper TTS service.

## Service Won't Start

### Symptom

```bash
sudo systemctl status hailo-piper.service
● hailo-piper.service - failed
```

### Common Causes

#### 1. Missing Piper TTS Model

**Check:**
```bash
ls -lah /var/lib/hailo-piper/models/
```

**Should see:**
- `en_US-lessac-medium.onnx`
- `en_US-lessac-medium.onnx.json`

**Fix:**
```bash
cd system_services/hailo-piper
sudo ./install.sh --download-model
```

Or manually download from [Piper Releases](https://github.com/rhasspy/piper/releases):
```bash
cd /var/lib/hailo-piper/models
sudo wget https://github.com/rhasspy/piper/releases/latest/download/en_US-lessac-medium.onnx
sudo wget https://github.com/rhasspy/piper/releases/latest/download/en_US-lessac-medium.onnx.json
sudo chown hailo-piper:hailo-piper *.onnx*
```

#### 2. Missing Python Dependencies

**Check:**
```bash
python3 -c "import piper"
```

**Error:** `ModuleNotFoundError: No module named 'piper'`

**Fix:**
```bash
pip3 install piper-tts --break-system-packages
```

#### 3. Port Already in Use

**Check:**
```bash
sudo ss -lntp | grep :5002
```

**Fix:**
Change port in `/etc/hailo/hailo-piper.yaml`:
```yaml
server:
  port: 5003  # Use different port
```

Then restart:
```bash
sudo systemctl restart hailo-piper.service
```

#### 4. Permission Issues

**Check logs:**
```bash
journalctl -u hailo-piper.service -n 50 --no-pager
```

**Look for:** Permission denied errors

**Fix:**
```bash
sudo chown -R hailo-piper:hailo-piper /var/lib/hailo-piper
sudo chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-piper
```

## Health Check Fails

### Symptom

```bash
curl http://localhost:5002/health
# No response or connection refused
```

### Diagnosis

1. **Check if service is running:**
```bash
sudo systemctl is-active hailo-piper.service
```

2. **Check listening ports:**
```bash
sudo ss -lntp | grep python3
```

3. **Check logs:**
```bash
journalctl -u hailo-piper.service -f
```

### Fixes

**Service not running:**
```bash
sudo systemctl start hailo-piper.service
```

**Wrong port:**
Check config at `/etc/hailo/hailo-piper.yaml` and verify port number.

**Firewall blocking:**
```bash
sudo ufw allow 5002/tcp
```

## Synthesis Fails

### Symptom

```bash
curl -X POST http://localhost:5002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "test"}' \
  --output test.wav
# Returns error or empty file
```

### Common Causes

#### 1. Wrong Piper TTS Version

**Error:** `ImportError: cannot import name 'espeakbridge' from 'piper'`

**Or:** `wave.Error: # channels not specified`

**Cause:** piper-tts 1.4.0 is broken - it changed from self-contained wheel to pure Python package requiring system espeak-ng, and has phoneme handling bugs.

**Check version:**
```bash
/opt/hailo-piper/venv/bin/python3 -c "import piper; print(piper.__version__)"
```

**Should be:** `1.3.0`

**Fix:** Downgrade to working version:
```bash
sudo /opt/hailo-piper/venv/bin/pip install piper-tts==1.3.0 --force-reinstall --no-cache-dir
sudo systemctl restart hailo-piper.service
```

**Prevention:** The installer pins to `piper-tts==1.3.0` in requirements.txt. See [Hailo Community post](https://community.hailo.ai/t/piper-tts-1-4-0-tts-synthesis-playback-failed-channels-not-specified/18701) for technical details.

#### 2. Model Not Loaded

**Check health endpoint:**
```bash
curl http://localhost:5002/health | python3 -m json.tool
```

**Look for:** `"model_loaded": false`

**Fix:** Restart service after ensuring model files exist:
```bash
sudo systemctl restart hailo-piper.service
```

#### 2. Text Too Long

**Error:** `Text too long (max 5000 characters)`

**Fix:** Split text into smaller chunks:
```python
def chunk_text(text, max_len=4500):
    sentences = text.split('. ')
    chunks = []
    current = ""
    
    for sentence in sentences:
        if len(current) + len(sentence) < max_len:
            current += sentence + ". "
        else:
            chunks.append(current)
            current = sentence + ". "
    
    if current:
        chunks.append(current)
    
    return chunks
```

#### 3. Invalid JSON

**Error:** `No JSON body`

**Fix:** Ensure proper Content-Type header and valid JSON:
```bash
curl -X POST http://localhost:5002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "test"}' \
  --output test.wav
```

#### 4. Out of Memory

**Check logs:**
```bash
journalctl -u hailo-piper.service | grep -i "memory\|oom"
```

**Fix:**
Increase memory limit in `/etc/systemd/system/hailo-piper.service`:
```ini
MemoryMax=3G  # Increase from 2G
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart hailo-piper.service
```

## Slow Synthesis

### Symptom

Synthesis takes >5 seconds for short phrases.

### Diagnosis

**Check CPU usage:**
```bash
top -p $(pgrep -f hailo_piper_service)
```

**Check concurrent requests:**
```bash
journalctl -u hailo-piper.service -f
# Look for queued requests
```

### Fixes

#### 1. Model Size Too Large

**Solution:** Use a smaller model (e.g., "low" quality instead of "high"):
```bash
cd /var/lib/hailo-piper/models
sudo wget https://github.com/rhasspy/piper/releases/latest/download/en_US-lessac-low.onnx
sudo wget https://github.com/rhasspy/piper/releases/latest/download/en_US-lessac-low.onnx.json
```

Update `/etc/hailo/hailo-piper.yaml`:
```yaml
piper:
  model_path: /var/lib/hailo-piper/models/en_US-lessac-low.onnx
```

Restart:
```bash
sudo systemctl restart hailo-piper.service
```

#### 2. CPU Throttling

**Check temperature:**
```bash
vcgencmd measure_temp
```

**Solution:** Add cooling or reduce CPU quota:
```ini
CPUQuota=50%  # Reduce from 80%
```

#### 3. Concurrent Requests

**Cause:** Multiple requests serialized due to model lock

**Solution:** Deploy multiple service instances on different ports

## Audio Quality Issues

### Symptom

Generated audio sounds robotic, garbled, or unnatural.

### Fixes

#### 1. Adjust Synthesis Parameters

Edit `/etc/hailo/hailo-piper.yaml`:
```yaml
piper:
  volume: 1.0
  length_scale: 1.1  # Slower = more natural (1.0 = default)
  noise_scale: 0.667  # Variability
  noise_w_scale: 0.8  # Duration variability
```

Restart:
```bash
sudo systemctl restart hailo-piper.service
```

#### 2. Try Different Voice Model

Download alternative voice:
```bash
cd /var/lib/hailo-piper/models
# Female voice
sudo wget https://github.com/rhasspy/piper/releases/latest/download/en_US-amy-medium.onnx
sudo wget https://github.com/rhasspy/piper/releases/latest/download/en_US-amy-medium.onnx.json
```

Update config and restart.

#### 3. Text Preprocessing

Some characters or patterns can cause artifacts. Try:
- Removing special characters
- Expanding abbreviations
- Adding punctuation for natural phrasing

## Service Crashes

### Symptom

Service stops unexpectedly; systemd restarts it automatically.

### Diagnosis

**Check crash logs:**
```bash
journalctl -u hailo-piper.service --since "1 hour ago" | grep -i "error\|exception\|traceback"
```

**Check core dumps:**
```bash
coredumpctl list
coredumpctl info
```

### Common Causes

#### 1. Memory Leak

**Fix:** Restart service periodically (workaround):
```bash
# Add to crontab
0 3 * * * systemctl restart hailo-piper.service
```

Or increase memory limit.

#### 2. Uncaught Exception

**Fix:** Check logs for Python traceback, report issue if reproducible.

#### 3. Resource Exhaustion

**Fix:** Add resource limits in systemd unit file.

## Configuration Issues

### Symptom

Changes to `/etc/hailo/hailo-piper.yaml` not taking effect.

### Fix

Always restart service after config changes:
```bash
sudo systemctl restart hailo-piper.service
```

Verify config syntax:
```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/hailo/hailo-piper.yaml'))"
```

## Installation Issues

### Symptom

`./install.sh` fails.

### Common Errors

#### 1. Not Running as Root

**Error:** `This script must be run as root`

**Fix:**
```bash
sudo ./install.sh
```

#### 2. Missing wget

**Error:** `wget not found`

**Fix:**
```bash
sudo apt install wget
```

#### 3. Network Issues

**Error:** Failed to download model

**Fix:**
- Check internet connection
- Manually download from browser and copy to `/var/lib/hailo-piper/models/`

## Logs and Diagnostics

### View Live Logs

```bash
journalctl -u hailo-piper.service -f
```

### View Recent Errors

```bash
journalctl -u hailo-piper.service -p err -n 50 --no-pager
```

### Export Logs for Bug Report

```bash
journalctl -u hailo-piper.service --since "1 day ago" > hailo-piper.log
```

### Enable Debug Logging

Edit `/etc/hailo/hailo-piper.yaml`:
```yaml
logging:
  level: DEBUG
```

Restart service.

### Check Service Status

```bash
sudo systemctl status hailo-piper.service --no-pager -l
```

## Performance Benchmarking

### Test Synthesis Speed

```bash
time curl -X POST http://localhost:5002/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "The quick brown fox jumps over the lazy dog."}' \
  --output /dev/null --silent
```

### Monitor Resource Usage

```bash
watch -n 1 'ps aux | grep hailo_piper_service'
```

Or use htop:
```bash
htop -p $(pgrep -f hailo_piper_service)
```

## Getting Help

### Check Documentation

- [README.md](README.md) - Installation and usage
- [API_SPEC.md](API_SPEC.md) - API reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design

### Collect Diagnostic Info

```bash
# System info
uname -a
cat /etc/os-release

# Service status
sudo systemctl status hailo-piper.service

# Recent logs
journalctl -u hailo-piper.service -n 100 --no-pager

# Configuration
cat /etc/hailo/hailo-piper.yaml

# Model files
ls -lah /var/lib/hailo-piper/models/

# Python environment
python3 --version
pip3 list | grep -i piper

# Resource usage
free -h
df -h /var/lib/hailo-piper
```

### Report Issues

When reporting issues, include:
1. Symptom description
2. Steps to reproduce
3. Diagnostic output (see above)
4. Expected vs. actual behavior

## Known Limitations

- **Streaming:** No real-time audio streaming (full synthesis before response)
- **Formats:** WAV only (no MP3/OGG yet)
- **Voices:** Single voice per service instance
- **Concurrency:** Serialized synthesis (model lock)
- **Text length:** 5000 character limit per request

## Quick Validation

Run the verification script:
```bash
cd system_services/hailo-piper
sudo ./verify.sh
```

This tests:
- systemd service status
- Health endpoint
- Synthesis functionality
- Audio output validation
