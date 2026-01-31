# Hailo Depth Estimation Troubleshooting

Common issues and solutions for `hailo-depth` service.

---

## Quick Diagnostics

```bash
# Check service status
sudo systemctl status hailo-depth.service

# View recent logs
sudo journalctl -u hailo-depth.service -n 100 --no-pager

# Test health endpoint
curl http://localhost:11436/health

# Verify NPU device
ls -l /dev/hailo0
hailortcli fw-control identify

# Check resource usage
systemd-cgtop
```

---

## Installation Issues

### Issue: `/dev/hailo0` not found

**Symptom:** Installer fails with "Install Hailo driver" error.

**Cause:** Hailo kernel driver not installed.

**Solution:**

```bash
sudo apt update
sudo apt install dkms hailo-h10-all
sudo reboot
```

**Verify:**

```bash
ls -l /dev/hailo0
hailortcli fw-control identify
```

---

### Issue: Permission denied on `/dev/hailo0`

**Symptom:** Service fails to start with "Permission denied" error.

**Cause:** User `hailo-depth` not in Hailo device group.

**Solution:**

```bash
# Find device group
DEVICE_GROUP=$(stat -c '%G' /dev/hailo0)

# Add user to group
sudo usermod -aG "${DEVICE_GROUP}" hailo-depth

# Restart service
sudo systemctl restart hailo-depth.service
```

**Verify:**

```bash
groups hailo-depth
```

---

### Issue: Missing Python packages

**Symptom:** Installer fails with "Missing required Python packages" error.

**Cause:** Required dependencies not installed.

**Solution:**

```bash
# Via pip (user install)
pip3 install aiohttp numpy pillow pyyaml matplotlib

# Or via apt (system-wide)
sudo apt install python3-aiohttp python3-numpy python3-pil python3-yaml python3-matplotlib
```

**Verify:**

```bash
python3 -c "import aiohttp, numpy, PIL, yaml; print('OK')"
```

---

### Issue: Port already in use

**Symptom:** Service starts but health check fails; logs show "Address already in use".

**Cause:** Another service is using port 11436.

**Solution:**

```bash
# Find process using port
sudo ss -lntp | grep 11436

# Change port in config
sudo nano /etc/hailo/hailo-depth.yaml
# Update server.port to a different value (e.g., 11437)

# Re-render config
sudo python3 /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-depth/render_config.py \
  --input /etc/hailo/hailo-depth.yaml \
  --output /etc/xdg/hailo-depth/hailo-depth.json

# Restart service
sudo systemctl restart hailo-depth.service
```

---

## Runtime Issues

### Issue: Service fails to start

**Symptom:** `systemctl status hailo-depth.service` shows "failed" or "activating".

**Diagnostic Steps:**

```bash
# View full logs
sudo journalctl -u hailo-depth.service -n 100 --no-pager

# Check for common errors
sudo journalctl -u hailo-depth.service -p err -n 20
```

**Common Causes:**

1. **Missing HEF file:**
   - **Error:** "HEF path is invalid or missing"
   - **Solution:** Download or install depth model:
     ```bash
     # TODO: Add download instructions for scdepthv3.hef
     # Place in /var/lib/hailo-depth/models/
     ```

2. **NPU initialization failure:**
   - **Error:** "Model initialization failed"
   - **Solution:** Check NPU availability:
     ```bash
     hailortcli fw-control identify
     # If fails, try: sudo modprobe hailo_pci
     # Or reboot: sudo reboot
     ```

3. **Config parse error:**
   - **Error:** "Failed to load config"
   - **Solution:** Validate YAML syntax:
     ```bash
     python3 -c "import yaml; yaml.safe_load(open('/etc/hailo/hailo-depth.yaml'))"
     # Fix syntax errors, then re-render
     ```

---

### Issue: Health check returns 503

**Symptom:** `curl http://localhost:11436/health` returns `{"ready": false, "reason": "model_loading"}`.

**Cause:** Model is still loading (normal during first 10-20 seconds after startup).

**Solution:**

```bash
# Wait and retry
sleep 5
curl http://localhost:11436/health/ready

# If persists, check logs
sudo journalctl -u hailo-depth.service -f
```

**If model loading fails:**
- Check HEF file exists and is readable
- Verify NPU is not in use by another service
- Check memory availability: `free -h`

---

### Issue: Inference returns 500 error

**Symptom:** API request returns `{"error": {"message": "...", "type": "internal_error"}}`.

**Diagnostic:**

```bash
# View detailed error
sudo journalctl -u hailo-depth.service -f
# Then send a request and watch logs
```

**Common Causes:**

1. **Invalid image format:**
   - **Error:** "cannot identify image file"
   - **Solution:** Ensure image is valid JPEG/PNG
   - **Test:** `file image.jpg` (should show image type)

2. **Image too large:**
   - **Error:** "Request Entity Too Large"
   - **Solution:** Resize image or increase `client_max_size` in `hailo_depth_server.py`

3. **Memory exhaustion:**
   - **Error:** "MemoryError" or service crashes
   - **Solution:** Check memory usage:
     ```bash
     systemd-cgtop
     # If high, reduce concurrent requests or increase MemoryMax in service unit
     ```

4. **NPU timeout:**
   - **Error:** "Inference timeout" or "Device busy"
   - **Solution:** Check if other services are using NPU:
     ```bash
     # List Hailo processes
     ps aux | grep hailo
     # Stop competing services if needed
     ```

---

### Issue: Slow inference time

**Symptom:** Requests take >100ms when expecting ~40-60ms.

**Diagnostic:**

```bash
# Check CPU throttling
vcgencmd measure_temp
vcgencmd get_throttled
# 0x0 = no throttling
# 0x1 = currently throttled
```

**Solutions:**

1. **Thermal throttling:**
   - **Cause:** Pi 5 overheating (>85°C)
   - **Solution:** Add cooling (heatsink, fan), reduce CPU quota

2. **CPU contention:**
   - **Cause:** Other services using CPU
   - **Check:** `top` or `htop`
   - **Solution:** Reduce CPU quota of other services

3. **Large images:**
   - **Cause:** High-resolution input images
   - **Solution:** Resize images before sending (640x480 recommended)

4. **I/O bottleneck:**
   - **Cause:** Slow SD card
   - **Solution:** Use faster storage (NVMe, USB SSD)

---

### Issue: Service crashes repeatedly

**Symptom:** `systemctl status hailo-depth.service` shows multiple restarts.

**Diagnostic:**

```bash
# View crash logs
sudo journalctl -u hailo-depth.service -n 200 --no-pager | grep -A 10 "ERROR"

# Check for OOM kills
sudo journalctl -k | grep -i "out of memory"
sudo journalctl -k | grep -i "killed process"
```

**Solutions:**

1. **Memory leak:**
   - **Symptom:** Memory usage grows over time
   - **Check:** `systemd-cgtop` while service runs
   - **Workaround:** Restart service periodically (systemd timer)
   - **Report:** File bug with logs

2. **NPU driver issue:**
   - **Symptom:** "Device I/O error" or kernel panics
   - **Check:** `dmesg | grep hailo`
   - **Solution:** Update Hailo driver:
     ```bash
     sudo apt update
     sudo apt install --only-upgrade hailo-h10-all
     sudo reboot
     ```

3. **Segmentation fault:**
   - **Symptom:** "Segmentation fault" in logs
   - **Cause:** HailoRT library bug or corrupted model
   - **Solution:** Reinstall HailoRT, re-download model

---

## Configuration Issues

### Issue: Config changes not applied

**Symptom:** Service still uses old config after editing `/etc/hailo/hailo-depth.yaml`.

**Cause:** JSON config not regenerated.

**Solution:**

```bash
# Re-render JSON from YAML
sudo python3 /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-depth/render_config.py \
  --input /etc/hailo/hailo-depth.yaml \
  --output /etc/xdg/hailo-depth/hailo-depth.json

# Restart service
sudo systemctl restart hailo-depth.service

# Verify new config loaded
curl http://localhost:11436/v1/info
```

---

### Issue: Invalid colormap name

**Symptom:** Request returns error: "Colormap '<name>' not found".

**Cause:** Invalid colormap specified in request or config.

**Solution:**

Use one of the supported colormaps:
- `viridis` (default)
- `plasma`
- `magma`
- `turbo`
- `jet`

**Example:**

```bash
curl -X POST http://localhost:11436/v1/depth/estimate \
  -F "image=@photo.jpg" \
  -F "colormap=viridis"
```

---

## Network Issues

### Issue: Cannot connect to service

**Symptom:** `curl http://localhost:11436/health` fails with "Connection refused".

**Diagnostic:**

```bash
# Check if service is running
sudo systemctl status hailo-depth.service

# Check port binding
sudo ss -lntp | grep 11436

# Check firewall
sudo iptables -L -n | grep 11436
```

**Solutions:**

1. **Service not running:**
   ```bash
   sudo systemctl start hailo-depth.service
   ```

2. **Wrong port:**
   ```bash
   # Check config
   cat /etc/xdg/hailo-depth/hailo-depth.json | grep port
   # Use correct port in curl
   ```

3. **Firewall blocking:**
   ```bash
   # Allow port (if external access needed)
   sudo ufw allow 11436/tcp
   # Or restrict to localhost (recommended)
   sudo ufw allow from 127.0.0.1 to any port 11436
   ```

---

### Issue: Timeout on external access

**Symptom:** Service works on localhost but times out from other machines.

**Cause:** Service bound to `127.0.0.1` or firewall blocking.

**Solution:**

```bash
# Check bind address
cat /etc/hailo/hailo-depth.yaml | grep host
# Should be: 0.0.0.0 for external access

# If 127.0.0.1, change to 0.0.0.0
sudo nano /etc/hailo/hailo-depth.yaml
# Update server.host: 0.0.0.0

# Re-render and restart
sudo python3 /home/gregm/raspberry_pi_hailo_ai_services/system_services/hailo-depth/render_config.py \
  --input /etc/hailo/hailo-depth.yaml \
  --output /etc/xdg/hailo-depth/hailo-depth.json
sudo systemctl restart hailo-depth.service

# Allow firewall (if needed)
sudo ufw allow 11436/tcp
```

---

## Debugging Tools

### Enable Debug Logging

Edit `hailo_depth_server.py` and change log level:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
```

Then:

```bash
sudo systemctl restart hailo-depth.service
sudo journalctl -u hailo-depth.service -f
```

### Manual Service Test

Run service manually (not via systemd):

```bash
sudo -u hailo-depth /usr/local/bin/hailo-depth-server
# Watch output for errors
```

### HailoRT Diagnostics

```bash
# Device info
hailortcli fw-control identify

# Scan for devices
hailortcli scan

# Check HEF compatibility
hailortcli parse-hef /path/to/model.hef
```

### Resource Monitoring

```bash
# Real-time resource usage
systemd-cgtop

# Service-specific stats
systemctl show hailo-depth.service --property=MemoryCurrent
systemctl show hailo-depth.service --property=CPUUsageNSec

# System temperature
watch -n 1 vcgencmd measure_temp
```

---

## Getting Help

### Collect Diagnostic Information

```bash
#!/bin/bash
# Save as: collect-diag.sh

OUTPUT="hailo-depth-diag-$(date +%Y%m%d-%H%M%S).txt"

{
  echo "=== System Info ==="
  uname -a
  cat /etc/os-release
  
  echo -e "\n=== Hailo Device ==="
  ls -l /dev/hailo0
  hailortcli fw-control identify || echo "hailortcli failed"
  
  echo -e "\n=== Service Status ==="
  systemctl status hailo-depth.service
  
  echo -e "\n=== Recent Logs ==="
  journalctl -u hailo-depth.service -n 100 --no-pager
  
  echo -e "\n=== Configuration ==="
  cat /etc/hailo/hailo-depth.yaml
  
  echo -e "\n=== Resource Usage ==="
  free -h
  systemctl show hailo-depth.service --property=MemoryCurrent
  
  echo -e "\n=== Network ==="
  ss -lntp | grep 11436
  
} > "${OUTPUT}"

echo "Diagnostics saved to ${OUTPUT}"
```

Run: `bash collect-diag.sh` and share the output file.

### Report Issues

Include:
1. Diagnostic output (above)
2. Steps to reproduce
3. Expected vs actual behavior
4. Raspberry Pi model and OS version
5. Hailo driver version: `dpkg -l | grep hailo`

---

## Known Limitations

1. **Single Request Processing:** Service handles one inference at a time (sequential)
2. **No Authentication:** API is open (use reverse proxy for auth)
3. **No TLS/HTTPS:** Plain HTTP (add reverse proxy for encryption)
4. **Monocular Only:** Stereo depth not yet implemented
5. **Relative Depth:** Values are scene-relative, not absolute distances
6. **Fixed Model:** Model cannot be changed without service modification

---

## Additional Resources

- **Service Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Documentation:** [API_SPEC.md](API_SPEC.md)
- **Installation Guide:** [README.md](README.md)
- **Hailo Developer Zone:** [developer.hailo.ai](https://developer.hailo.ai)
- **systemd Manual:** `man systemd.service`
- **journalctl Manual:** `man journalctl`
