# hailo-florence Troubleshooting Guide

Common issues and solutions for the Florence-2 Image Captioning Service.

---

## Service Won't Start

### Symptom
```bash
$ sudo systemctl status hailo-florence
● hailo-florence.service - Hailo Florence-2 Image Captioning Service
     Loaded: loaded
     Active: failed (Result: exit-code)
```

### Diagnosis

**Check logs:**
```bash
sudo journalctl -u hailo-florence -n 100 --no-pager
```

### Common Causes

#### 1. Hailo Device Not Found

**Error message:**
```
Failed to initialize Hailo device: /dev/hailo0 not found
```

**Solution:**
```bash
# Verify Hailo device
ls -l /dev/hailo0

# Check driver
hailortcli fw-control identify

# If device missing, reinstall driver
sudo apt install --reinstall hailo-h10-all
sudo reboot
```

#### 2. Model Files Missing

**Error message:**
```
FileNotFoundError: florence2_encoder.hef not found
```

**Solution:**
```bash
# Check model directory
ls -la /opt/hailo/florence/models/

# Re-run model download (if applicable)
# Or manually download models to /opt/hailo/florence/models/
```

#### 3. Python Dependencies Missing

**Error message:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution:**
```bash
# Reinstall dependencies
sudo pip3 install --break-system-packages fastapi uvicorn pillow transformers onnxruntime pyyaml aiofiles
```

#### 4. Permission Denied

**Error message:**
```
PermissionError: [Errno 13] Permission denied: '/dev/hailo0'
```

**Solution:**
```bash
# Verify user in video group
groups hailo-florence | grep video

# If missing, add to group
sudo usermod -a -G video hailo-florence

# Restart service
sudo systemctl restart hailo-florence
```

---

## Service Crashes After Starting

### Symptom
Service starts but crashes after a few seconds

### Diagnosis

**Check for OOM (Out of Memory):**
```bash
sudo journalctl -k | grep -i "killed process"
```

**Check memory usage:**
```bash
free -h
```

### Solutions

#### 1. Out of Memory

**If total used memory > 90%:**
```bash
# Stop other AI services
sudo systemctl stop hailo-ollama
sudo systemctl stop hailo-vision

# Increase swap (temporary)
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Restart florence service
sudo systemctl start hailo-florence
```

**Permanent solution:** Don't run florence + vision concurrently (see ARCHITECTURE.md)

#### 2. Model Loading Timeout

**If service takes > 120 seconds to start:**

Edit `/etc/systemd/system/hailo-florence.service`:
```ini
[Service]
TimeoutStartSec=300  # Increase from default
```

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart hailo-florence
```

---

## API Returns 503 Service Unavailable

### Symptom
```bash
$ curl http://localhost:8082/health
{"status":"unhealthy","model_loaded":false}
```

### Diagnosis

**Check service logs:**
```bash
sudo journalctl -u hailo-florence -f
```

### Common Causes

#### 1. Model Still Loading

**If logs show:**
```
Loading Florence-2 models...
```

**Solution:** Wait 1-2 minutes for model loading to complete. First start after installation can take 2-3 minutes.

#### 2. ONNX Runtime Error

**Error message:**
```
ONNXRuntimeError: Invalid graph
```

**Solution:**
```bash
# Reinstall onnxruntime
sudo pip3 install --break-system-packages --force-reinstall onnxruntime

# Restart service
sudo systemctl restart hailo-florence
```

---

## Slow Inference (> 2 seconds per image)

### Symptom
```json
{
  "caption": "...",
  "inference_time_ms": 2500  // Expected: 500-1000ms
}
```

### Diagnosis

**Check CPU throttling:**
```bash
vcgencmd measure_clock arm
vcgencmd measure_temp
```

**Check concurrent load:**
```bash
htop
```

### Solutions

#### 1. Thermal Throttling

**If temp > 80°C:**
```bash
# Check temperature
vcgencmd measure_temp

# Improve cooling
# - Add heatsink
# - Increase airflow
# - Reduce concurrent services
```

#### 2. Concurrent Services

**If multiple AI services running:**
```bash
# Check what's running
systemctl list-units | grep hailo

# Stop non-essential services
sudo systemctl stop hailo-vision  # If not needed
```

#### 3. CPU Governor

**Set performance mode:**
```bash
# Check current governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Set to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

---

## API Returns 400 Invalid Image Format

### Symptom
```bash
$ curl -X POST http://localhost:8082/v1/caption -d '{"image": "..."}'
{"error":"invalid_image_format","message":"Image must be base64-encoded JPEG or PNG"}
```

### Solutions

#### 1. Missing Data URI Prefix

**Incorrect:**
```json
{"image": "/9j/4AAQSkZJRg..."}
```

**Correct:**
```json
{"image": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."}
```

#### 2. Malformed Base64

**Verify base64 encoding:**
```bash
# Encode correctly
base64 -w0 image.jpg

# No line breaks in base64 string!
```

#### 3. Unsupported Format

**Supported formats:**
- JPEG (.jpg, .jpeg)
- PNG (.png)

**Not supported:**
- BMP, GIF, TIFF, WebP, etc.

**Conversion:**
```bash
# Convert to JPEG
convert image.bmp image.jpg
```

---

## High Memory Usage (> 4 GB)

### Symptom
```bash
$ systemctl show hailo-florence --property=MemoryCurrent
MemoryCurrent=4500000000  # > 4GB
```

### Solutions

#### 1. Memory Leak (Rare)

**Restart service:**
```bash
sudo systemctl restart hailo-florence
```

**Monitor memory:**
```bash
watch -n 5 'systemctl show hailo-florence --property=MemoryCurrent'
```

**If memory grows unbounded:** Report bug with logs

#### 2. Large Image Buffers

**If processing many large images:**

Edit `/etc/hailo/florence/config.yaml`:
```yaml
model:
  max_image_bytes: 5242880  # Reduce from 10MB to 5MB
```

Restart service:
```bash
sudo systemctl restart hailo-florence
```

---

## Can't Access API from Other Machines

### Symptom
```bash
# From another machine:
$ curl http://192.168.1.100:8082/health
curl: (7) Failed to connect
```

### Solutions

#### 1. Check Service Binding

**Verify config:**
```bash
grep "host:" /etc/hailo/florence/config.yaml

# Should be:
#   host: "0.0.0.0"  # NOT "127.0.0.1"
```

**If wrong, edit config and restart:**
```bash
sudo nano /etc/hailo/florence/config.yaml
sudo systemctl restart hailo-florence
```

#### 2. Firewall Blocking

**Check firewall:**
```bash
sudo iptables -L -n | grep 8082
```

**Allow port:**
```bash
sudo iptables -A INPUT -p tcp --dport 8082 -j ACCEPT
```

**Make persistent:**
```bash
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

#### 3. Network Route

**Verify connectivity:**
```bash
# On Pi:
ip addr show

# From other machine:
ping 192.168.1.100
```

---

## Service Logs Filled with Warnings

### Symptom
```
WARNING: Inference time exceeded threshold: 1520ms
WARNING: Memory usage approaching limit: 3.8GB
```

### Solutions

#### 1. Tune Warning Thresholds

Edit `/etc/hailo/florence/config.yaml`:
```yaml
logging:
  level: "ERROR"  # Reduce verbosity (was INFO)
```

#### 2. Adjust Performance Expectations

**These warnings are informational:**
- Inference time 1-2s is normal for Florence-2
- Memory usage 3-4GB is expected

**Disable specific warnings in code** (if needed)

---

## Model Produces Incorrect Captions

### Symptom
Captions are nonsensical or unrelated to image content

### Diagnosis

**Test with known-good images:**
```bash
# Download test image
wget https://example.com/test_image.jpg

# Generate caption
./verify.sh  # Includes test image
```

### Solutions

#### 1. Corrupted Model Files

**Re-download models:**
```bash
# Remove existing models
sudo rm -rf /opt/hailo/florence/models/*

# Re-run installation (will re-download)
sudo ./install.sh
```

#### 2. Wrong Model Variant

**Verify model files:**
```bash
ls -lh /opt/hailo/florence/models/
# Should see:
#   florence2_davit.onnx
#   florence2_encoder.hef
#   florence2_decoder.hef
#   tokenizer.json
```

#### 3. Image Preprocessing Issue

**Check image format:**
- Must be RGB (not grayscale, RGBA)
- Proper JPEG/PNG encoding
- Not corrupted

---

## Concurrent Services Conflicts

### Symptom
Multiple AI services running, all experiencing high latency or failures

### Diagnosis

**Check all running services:**
```bash
systemctl list-units | grep hailo
```

**Check total memory usage:**
```bash
free -h
```

### Solutions

#### 1. Memory Budget Exceeded

**Recommended combinations:**

✅ **Safe:**
- florence + ollama (6GB total)
- florence + clip (5GB total)

⚠️ **Tight:**
- florence + vision (7-8GB total)

❌ **Unsafe:**
- florence + ollama + vision (9-11GB)

**Stop conflicting services:**
```bash
sudo systemctl stop hailo-vision
sudo systemctl disable hailo-vision  # Don't start on boot
```

#### 2. Hailo Device Contention

**Hailo-10H supports concurrent inference**, but with shared resources:

**Monitor Hailo utilization:**
```bash
# Check which services are using Hailo
lsof /dev/hailo0
```

**Serial vs. Concurrent:**
- Florence encoder + decoder can run while Ollama is idle
- But sustained load on both will reduce throughput

**Solution:** Stagger workloads or run one service at a time

---

## Getting More Help

### Collect Diagnostic Information

```bash
# Create diagnostic report
cat > florence_diagnostics.txt << EOF
=== System Info ===
$(uname -a)
$(free -h)
$(vcgencmd measure_temp)

=== Service Status ===
$(systemctl status hailo-florence --no-pager)

=== Recent Logs ===
$(sudo journalctl -u hailo-florence -n 100 --no-pager)

=== Configuration ===
$(cat /etc/hailo/florence/config.yaml)

=== Hailo Device ===
$(hailortcli fw-control identify)
EOF

cat florence_diagnostics.txt
```

### Contact Support

- **GitHub Issues:** https://github.com/hailo-ai/hailo-rpi5-examples/issues
- **Documentation:** See README.md, API_SPEC.md, ARCHITECTURE.md
- **System Setup:** reference_documentation/system_setup.md

---

**Last Updated:** January 31, 2026  
**Version:** 1.0.0
