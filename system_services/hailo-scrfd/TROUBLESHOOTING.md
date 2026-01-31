# Hailo SCRFD Service Troubleshooting

Common issues and solutions for the SCRFD face detection service.

---

## Quick Diagnostics

### Check Service Status

```bash
# Service status
sudo systemctl status hailo-scrfd.service

# Recent logs
sudo journalctl -u hailo-scrfd.service -n 50 --no-pager

# Follow logs in real-time
sudo journalctl -u hailo-scrfd.service -f

# Run verification script
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-scrfd
sudo ./verify.sh
```

### Check Health Endpoint

```bash
curl http://localhost:5001/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "hailo-scrfd",
  "model_loaded": true,
  "model": "scrfd_2.5g_bnkps"
}
```

---

## Common Issues

### 1. Service Fails to Start

**Symptoms:**
```bash
$ sudo systemctl status hailo-scrfd.service
● hailo-scrfd.service - Hailo SCRFD (Face Detection...)
   Active: failed (Result: exit-code)
```

**Possible Causes & Solutions:**

#### a) Missing Python Dependencies

**Check:**
```bash
python3 -c "import yaml, numpy, cv2, flask"
```

**Fix:**
```bash
sudo apt install python3-yaml python3-numpy python3-pil python3-flask
pip3 install opencv-python
```

#### b) Hailo Device Not Found

**Check:**
```bash
ls -l /dev/hailo0
```

**Fix:**
```bash
sudo apt install dkms hailo-h10-all
sudo reboot
```

#### c) Permission Issues

**Check:**
```bash
sudo journalctl -u hailo-scrfd.service | grep -i permission
```

**Fix:**
```bash
# Get Hailo device group
HAILO_GROUP=$(stat -c '%G' /dev/hailo0)

# Add service user to group
sudo usermod -aG $HAILO_GROUP hailo-scrfd

# Restart service
sudo systemctl restart hailo-scrfd.service
```

#### d) Port Already in Use

**Check:**
```bash
sudo ss -lntp | grep :5001
```

**Fix:**
```bash
# Change port in config
sudo nano /etc/hailo/hailo-scrfd.yaml
# Update server.port to different value

sudo systemctl restart hailo-scrfd.service
```

---

### 2. Service Starts But Health Check Fails

**Symptoms:**
```bash
$ curl http://localhost:5001/health
curl: (7) Failed to connect to localhost port 5001: Connection refused
```

**Possible Causes:**

#### a) Service Still Initializing

Model loading takes 60-90 seconds.

**Check:**
```bash
# Check if Python process is running
ps aux | grep hailo_scrfd_service

# Wait and retry
sleep 30
curl http://localhost:5001/health
```

#### b) Service Crashed During Startup

**Check logs:**
```bash
sudo journalctl -u hailo-scrfd.service -n 100 --no-pager
```

Look for Python tracebacks or errors.

#### c) Config File Malformed

**Check:**
```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/hailo/hailo-scrfd.yaml'))"
```

**Fix:** Correct YAML syntax errors.

---

### 3. Face Detection Returns No Faces

**Symptoms:**
```json
{
  "faces": [],
  "num_faces": 0,
  "inference_time_ms": 18.5
}
```

**Possible Causes:**

#### a) Confidence Threshold Too High

**Fix:**
```bash
# Lower threshold in request
curl -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"...\", \"conf_threshold\": 0.3}"
```

Or adjust config:
```yaml
scrfd:
  conf_threshold: 0.3  # Default was 0.5
```

#### b) Image Too Small/Large

SCRFD works best on images with faces >50 pixels wide.

**Solution:** Resize images before sending.

#### c) Poor Image Quality

Low light, blur, extreme angles reduce detection accuracy.

**Solution:** Use better quality images or try the 10G model:
```yaml
scrfd:
  model: scrfd_10g_bnkps  # Higher accuracy
```

---

### 4. Slow Inference / Timeout

**Symptoms:**
```
ERROR: Request timeout after 30 seconds
```

**Possible Causes:**

#### a) CPU Throttling (Thermal)

**Check temperature:**
```bash
vcgencmd measure_temp
```

If >80°C, throttling may occur.

**Fix:**
- Add active cooling (fan)
- Reduce concurrent load
- Lower `CPUQuota` in systemd unit

#### b) Too Many Concurrent Requests

**Check logs for queue buildup:**
```bash
sudo journalctl -u hailo-scrfd.service | grep -i queue
```

**Fix:** Reduce client concurrency or increase worker threads:
```yaml
performance:
  worker_threads: 4  # Increase from 2
```

#### c) Large Image Size

Preprocessing 4K images takes time.

**Solution:** Downscale images before sending:
```bash
convert large.jpg -resize 1920x1080 medium.jpg
```

---

### 5. Memory Issues / OOM Kills

**Symptoms:**
```bash
$ sudo journalctl -u hailo-scrfd.service | grep -i "killed"
hailo-scrfd.service: Main process exited, code=killed, status=9/KILL
```

**Cause:** Service exceeded memory limit or system OOM killer activated.

**Check memory usage:**
```bash
systemctl show hailo-scrfd.service | grep MemoryCurrent
```

**Solutions:**

#### a) Increase Memory Limit

```bash
sudo nano /etc/systemd/system/hailo-scrfd.service
```

Change:
```ini
MemoryMax=3G  # Increase from 2G
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart hailo-scrfd.service
```

#### b) Reduce Concurrent Services

Stop other memory-heavy services:
```bash
sudo systemctl stop hailo-ollama.service  # LLM uses 4-6 GB
```

#### c) Use Lightweight Model

```yaml
scrfd:
  model: scrfd_2.5g_bnkps  # Instead of scrfd_10g_bnkps
```

---

### 6. Model Not Found

**Symptoms:**
```
ERROR: Failed to load SCRFD model: Model file not found
```

**Check hailo-apps:**
```bash
ls -l /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps/hailo_apps/postprocess/
```

**Fix:**
```bash
cd /home/gregm/raspberry_pi_hailo_ai_services
git submodule update --init --recursive hailo-apps
```

---

### 7. Landmarks Are Inaccurate

**Symptoms:**
Landmarks don't align well with facial features.

**Possible Causes:**

#### a) Face Pose Too Extreme

SCRFD optimized for near-frontal faces (±45°).

**Solution:** Filter by face angle or use pose-invariant model.

#### b) Low Resolution Faces

Faces <50 pixels wide have unreliable landmarks.

**Solution:** Detect only larger faces:
```python
# Post-filter by bbox size
faces = [f for f in result['faces'] if f['bbox'][2] > 50]
```

#### c) Partial Occlusion

Sunglasses, masks, hair covering face.

**Solution:** Check landmark confidence (if available) or use quality scoring.

---

### 8. Service Restart Loop

**Symptoms:**
```bash
$ sudo systemctl status hailo-scrfd.service
Active: activating (auto-restart) (Result: exit-code)
```

**Cause:** Service crashes repeatedly, systemd keeps restarting.

**Check crash logs:**
```bash
sudo journalctl -u hailo-scrfd.service -n 200 --no-pager
```

**Common Causes:**
- Python import error (missing module)
- Config file error (invalid YAML)
- Hailo device conflict (another service using it)

**Fix:** Address root cause, then restart:
```bash
sudo systemctl reset-failed hailo-scrfd.service
sudo systemctl restart hailo-scrfd.service
```

---

## Performance Tuning

### Optimize for Speed

1. **Use lightweight model:**
   ```yaml
   scrfd:
     model: scrfd_2.5g_bnkps  # 50-60 fps
   ```

2. **Reduce NMS threshold:**
   ```yaml
   scrfd:
     nms_threshold: 0.3  # Fewer duplicates, faster NMS
   ```

3. **Limit max faces:**
   ```yaml
   detection:
     max_faces: 5  # Stop after 5 faces
   ```

4. **Downscale input images** before sending to API.

### Optimize for Accuracy

1. **Use high-accuracy model:**
   ```yaml
   scrfd:
     model: scrfd_10g_bnkps  # 92% AP
   ```

2. **Lower confidence threshold:**
   ```yaml
   scrfd:
     conf_threshold: 0.3  # Detect more faces (more false positives)
   ```

3. **Send high-resolution images** (but <2 MB recommended).

---

## Debugging Tools

### Test with Mock Model

Set service to use mock model for testing API without Hailo:

**Edit service file:**
```bash
sudo nano /opt/hailo-scrfd/hailo_scrfd_service.py
```

Uncomment mock model initialization in `_use_mock_model()` method.

### Manual Inference Test

```bash
python3 <<'PY'
import cv2
import numpy as np
from hailo_apps.postprocess.cpp import scrfd

# Load image
img = cv2.imread('test.jpg')
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# Initialize model
detector = scrfd.SCRFD(model_path='scrfd_2.5g_bnkps.hef')

# Detect
faces = detector.detect(img_rgb)
print(f"Detected {len(faces)} faces")
PY
```

### Port Conflict Resolution

```bash
# Find process using port 5001
sudo lsof -i :5001

# Kill if necessary
sudo kill <PID>

# Or change port in config
sudo nano /etc/hailo/hailo-scrfd.yaml
```

---

## Log Analysis

### Find Errors

```bash
sudo journalctl -u hailo-scrfd.service -p err --no-pager
```

### Check Full Request Cycle

```bash
# Enable debug logging
sudo nano /etc/hailo/hailo-scrfd.yaml
# Set: logging.level: DEBUG

sudo systemctl restart hailo-scrfd.service

# Watch debug logs
sudo journalctl -u hailo-scrfd.service -f
```

### Measure Latency

```bash
time curl -X POST http://localhost:5001/v1/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"data:image/jpeg;base64,$(base64 -w0 < test.jpg)\"}"
```

---

## Configuration Validation

### Validate YAML Syntax

```bash
python3 -c "
import yaml
with open('/etc/hailo/hailo-scrfd.yaml') as f:
    config = yaml.safe_load(f)
print('Config valid')
print(config)
"
```

### Test Config Rendering

```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-scrfd
python3 render_config.py \
  --input /etc/hailo/hailo-scrfd.yaml \
  --output /tmp/test-config.json

cat /tmp/test-config.json
```

---

## Advanced Debugging

### Enable HailoRT Logging

```bash
# Edit service file
sudo nano /etc/systemd/system/hailo-scrfd.service

# Add environment variable
Environment=HAILO_LOG_LEVEL=debug

sudo systemctl daemon-reload
sudo systemctl restart hailo-scrfd.service
```

### Check HailoRT Version

```bash
hailortcli fw-control identify
dpkg -l | grep hailo
```

### Verify Model HEF

```bash
hailortcli parse-hef /path/to/scrfd.hef
```

---

## Getting Help

### Collect Diagnostic Info

```bash
#!/bin/bash
# Save as collect_diagnostics.sh

echo "=== Service Status ===" > diagnostics.txt
sudo systemctl status hailo-scrfd.service >> diagnostics.txt

echo -e "\n=== Recent Logs ===" >> diagnostics.txt
sudo journalctl -u hailo-scrfd.service -n 100 --no-pager >> diagnostics.txt

echo -e "\n=== Config ===" >> diagnostics.txt
cat /etc/hailo/hailo-scrfd.yaml >> diagnostics.txt

echo -e "\n=== Memory ===" >> diagnostics.txt
systemctl show hailo-scrfd.service | grep Memory >> diagnostics.txt

echo -e "\n=== Health Check ===" >> diagnostics.txt
curl -s http://localhost:5001/health >> diagnostics.txt

echo "Diagnostics saved to diagnostics.txt"
```

### Report Issue

Include:
1. Service logs (`journalctl` output)
2. Config file contents
3. System info (CPU, RAM, OS version)
4. Hailo driver version (`hailortcli fw-control identify`)
5. Steps to reproduce

---

## See Also

- [README.md](README.md) — Installation and usage
- [API_SPEC.md](API_SPEC.md) — API documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design
