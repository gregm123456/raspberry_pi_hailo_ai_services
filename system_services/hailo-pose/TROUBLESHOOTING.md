# Hailo Pose Troubleshooting Guide

## Common Issues

### Service Won't Start

#### Problem: `/dev/hailo0 not found`

**Symptoms:**
```
Error: /dev/hailo0 not found. Install Hailo driver
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

**Expected output:**
```
/dev/hailo0 exists
Hailo firmware version: 4.x.x
```

---

#### Problem: Port already in use

**Symptoms:**
```
Error: Address already in use (port 11436)
```

**Solution 1: Check what's using the port**
```bash
sudo ss -lntp | grep 11436
# or
sudo lsof -i :11436
```

**Solution 2: Change port**
Edit `/etc/hailo/hailo-pose.yaml`:
```yaml
server:
  port: 11437  # Use different port
```

Then re-render config and restart:
```bash
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-pose
sudo python3 render_config.py \
  --input /etc/hailo/hailo-pose.yaml \
  --output /etc/xdg/hailo-pose/hailo-pose.json
sudo systemctl restart hailo-pose.service
```

---

#### Problem: Python dependencies missing

**Symptoms:**
```
Error: Missing required package: No module named 'aiohttp'
```

**Solution:**
```bash
sudo apt install python3-aiohttp python3-yaml
# or
pip3 install aiohttp pyyaml
```

---

#### Problem: Permission denied for `/dev/hailo0`

**Symptoms:**
```
Error: Cannot access /dev/hailo0: Permission denied
```

**Solution:**
```bash
# Check device group
stat -c '%G' /dev/hailo0

# Add user to device group (usually 'hailo' or 'video')
sudo usermod -aG $(stat -c '%G' /dev/hailo0) hailo-pose

# Restart service
sudo systemctl restart hailo-pose.service
```

---

### Service Starts But Health Check Fails

#### Problem: Service not responding

**Check service status:**
```bash
sudo systemctl status hailo-pose.service
```

**Check logs:**
```bash
sudo journalctl -u hailo-pose.service -n 100 --no-pager
```

**Test health endpoint:**
```bash
curl -v http://localhost:11436/health
```

**Common causes:**
1. **Service still loading:** Wait 5-10 seconds after start
2. **Model not found:** Check model path in logs
3. **Memory allocation failed:** Check available memory (`free -h`)

---

### Inference Errors

#### Problem: "Invalid base64" error

**Symptoms:**
```json
{
  "error": {
    "message": "Invalid base64: ...",
    "type": "invalid_request_error"
  }
}
```

**Solution:**
Ensure base64 encoding is correct:
```bash
# Correct:
base64 -w 0 image.jpg  # No line wraps

# For data URI, strip prefix:
base64 -w 0 image.jpg | sed 's/^/data:image\/jpeg;base64,/'
```

---

#### Problem: "Model not loaded" error

**Symptoms:**
```json
{
  "error": {
    "message": "Model not loaded",
    "type": "internal_error"
  }
}
```

**Check readiness:**
```bash
curl http://localhost:11436/health/ready
```

**If not ready:**
- Wait for model loading to complete
- Check logs for loading errors: `journalctl -u hailo-pose.service -n 50`
- Verify model files exist in `/var/lib/hailo-pose/resources/models/hailo10h/`

---

#### Problem: Very slow inference (>1 second)

**Possible causes:**

1. **CPU preprocessing bottleneck:**
   - Large image input (resize before sending)
   - Inefficient image decoding

2. **Model not using NPU:**
   - Check HailoRT is installed: `python3 -c "from hailo import HailoRT"`
   - Verify NPU is active: `hailortcli fw-control identify`

3. **Thermal throttling:**
   - Check temperature: `vcgencmd measure_temp`
   - If >80°C, add cooling or reduce load

**Solutions:**
```bash
# Resize images before sending
convert large.jpg -resize 640x640 resized.jpg
curl -X POST http://localhost:11436/v1/pose/detect -F "image=@resized.jpg"

# Check NPU utilization
watch -n 1 'hailortcli fw-control identify'

# Monitor temperature
watch -n 1 'vcgencmd measure_temp'
```

---

### Memory Issues

#### Problem: Service crashes with no logs

**Symptoms:**
- Service stops unexpectedly
- systemd shows "Main process exited"
- No error messages in logs

**Check OOM (Out of Memory):**
```bash
dmesg | grep -i 'killed process'
# or
journalctl -k | grep -i 'out of memory'
```

**Solution:**
Reduce memory usage:

1. **Edit systemd drop-in:**
   ```bash
   sudo systemctl edit hailo-pose.service
   ```

   Add:
   ```ini
   [Service]
   MemoryMax=1.5G
   ```

2. **Use smaller model:**
   Edit `/etc/hailo/hailo-pose.yaml`:
   ```yaml
   model:
     name: "yolov8n-pose"  # Nano model (smaller, faster)
   ```

3. **Reduce max detections:**
   ```yaml
   inference:
     max_detections: 5  # Down from 10
   ```

4. **Restart service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart hailo-pose.service
   ```

---

#### Problem: "Cannot allocate memory" during inference

**Symptoms:**
```
Error: Cannot allocate memory for inference
```

**Check available memory:**
```bash
free -h
```

**Check Hailo NPU memory:**
```bash
hailortcli fw-control identify
```

**Solutions:**
1. Stop other Hailo services temporarily
2. Use on-demand loading (`keep_alive: 0`) instead of persistent
3. Use smaller model variant (yolov8n-pose)

---

### Configuration Issues

#### Problem: Config changes not taking effect

**Check config rendering:**
```bash
# Verify YAML config
cat /etc/hailo/hailo-pose.yaml

# Re-render JSON
cd /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-pose
sudo python3 render_config.py \
  --input /etc/hailo/hailo-pose.yaml \
  --output /etc/xdg/hailo-pose/hailo-pose.json

# Verify JSON config
cat /etc/xdg/hailo-pose/hailo-pose.json

# Restart service
sudo systemctl restart hailo-pose.service
```

---

#### Problem: Invalid YAML syntax

**Symptoms:**
```
Error: Failed to parse YAML: ...
```

**Solution:**
Validate YAML syntax:
```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/hailo/hailo-pose.yaml'))"
```

Common issues:
- Incorrect indentation (use spaces, not tabs)
- Missing colons
- Unquoted strings with special characters

---

### Performance Issues

#### Problem: High CPU usage

**Check CPU quota:**
```bash
systemctl show hailo-pose.service -p CPUQuotaPerSecUSec
```

**Adjust CPU quota:**
```bash
sudo systemctl edit hailo-pose.service
```

Add:
```ini
[Service]
CPUQuota=60%  # Reduce from 80%
```

Restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart hailo-pose.service
```

---

#### Problem: Low throughput (<10 FPS)

**Possible causes:**

1. **Sequential requests:** Use concurrent requests
   ```bash
   # Parallel requests
   for i in {1..5}; do
     curl -X POST http://localhost:11436/v1/pose/detect \
       -F "image=@person.jpg" &
   done
   wait
   ```

2. **Large images:** Resize before sending
   ```bash
   convert large.jpg -resize 640x480 small.jpg
   ```

3. **High confidence thresholds:** Lower thresholds to reduce post-processing
   ```yaml
   inference:
     confidence_threshold: 0.3  # Down from 0.5
   ```

---

### Network Issues

#### Problem: Cannot reach service from another machine

**Check firewall:**
```bash
sudo ufw status
# If active, allow port:
sudo ufw allow 11436/tcp
```

**Check service binding:**
```bash
sudo ss -lntp | grep 11436
```

Should show `0.0.0.0:11436` (all interfaces).

If showing `127.0.0.1:11436`, edit config:
```yaml
server:
  host: 0.0.0.0  # Bind to all interfaces
```

---

### Debugging Workflows

#### Full diagnostic check

```bash
#!/bin/bash
echo "=== Hailo Device ==="
ls -l /dev/hailo0
hailortcli fw-control identify

echo -e "\n=== Service Status ==="
systemctl status hailo-pose.service

echo -e "\n=== Recent Logs ==="
journalctl -u hailo-pose.service -n 20 --no-pager

echo -e "\n=== Memory Usage ==="
free -h

echo -e "\n=== Temperature ==="
vcgencmd measure_temp

echo -e "\n=== Network Ports ==="
sudo ss -lntp | grep 11436

echo -e "\n=== Health Check ==="
curl -s http://localhost:11436/health | jq

echo -e "\n=== Readiness Check ==="
curl -s http://localhost:11436/health/ready | jq
```

Save as `diagnose.sh`, run with `bash diagnose.sh`

---

## Getting Help

### Collect diagnostic information

```bash
# System info
uname -a
cat /etc/os-release

# Hailo driver
dpkg -l | grep hailo

# Service logs
sudo journalctl -u hailo-pose.service -n 200 --no-pager > pose-service.log

# Config
cat /etc/hailo/hailo-pose.yaml
cat /etc/xdg/hailo-pose/hailo-pose.json

# Device info
hailortcli fw-control identify
ls -l /dev/hailo0
```

### Report issues

Include:
1. Error message or unexpected behavior
2. Service logs (from journalctl)
3. Config files
4. System info (OS version, Hailo driver version)
5. Steps to reproduce

---

## Prevention Best Practices

1. **Monitor Resources:**
   ```bash
   # Add to cron for daily monitoring
   journalctl -u hailo-pose.service --since "24 hours ago" | grep -i error
   ```

2. **Test Changes:**
   ```bash
   # Before deploying config changes
   python3 render_config.py --input new-config.yaml --output /tmp/test.json
   ```

3. **Backup Configs:**
   ```bash
   sudo cp /etc/hailo/hailo-pose.yaml /etc/hailo/hailo-pose.yaml.backup
   ```

4. **Health Monitoring:**
   Add to system monitoring (e.g., Prometheus):
   ```bash
   # Check health every 60 seconds
   */1 * * * * curl -f http://localhost:11436/health || systemctl restart hailo-pose.service
   ```

5. **Log Rotation:**
   Ensure journald is configured to rotate logs:
   ```bash
   sudo journalctl --vacuum-time=7d  # Keep last 7 days
   ```
