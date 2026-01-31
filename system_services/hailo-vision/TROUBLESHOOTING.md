# Hailo Vision Service Troubleshooting

## Common Issues & Solutions

### Installation & Startup

#### 1. "Missing required command python3"
**Error:** `ERROR: Missing required command: python3`

**Cause:** Python 3 not installed.

**Solution:**
```bash
sudo apt update
sudo apt install python3 python3-yaml
```

---

#### 2. "/dev/hailo0 not found"
**Error:** `ERROR: /dev/hailo0 not found. Install Hailo driver: sudo apt install dkms hailo-h10-all`

**Cause:** Hailo-10H kernel driver not installed.

**Solution:**
1. Install the driver:
   ```bash
   sudo apt install dkms hailo-h10-all
   sudo reboot
   ```
2. Verify device:
   ```bash
   ls -l /dev/hailo0
   hailortcli fw-control identify
   ```

---

#### 3. Service fails to start with "Permission denied"
**Error:** `Permission denied: /dev/hailo0`

**Cause:** The `hailo-vision` user doesn't have permissions to access `/dev/hailo0`.

**Solution:**
1. Check the device group:
   ```bash
   ls -l /dev/hailo0
   # Output: brw-rw---- 1 root hailo-devices 511, 0 Jan 31 10:00 /dev/hailo0
   ```
2. Re-run the installer to configure user groups:
   ```bash
   sudo ./install.sh
   ```
3. If already installed, manually add user to device group:
   ```bash
   sudo usermod -aG hailo-devices hailo-vision
   sudo systemctl restart hailo-vision.service
   ```

---

#### 4. "Port 11435 already in use"
**Error:** `WARNING: Port 11435 is already in use. Update /etc/hailo/hailo-vision.yaml if needed.`

**Cause:** Another service is using port 11435.

**Solution:**
1. Find the process using the port:
   ```bash
   sudo lsof -i :11435
   # or
   sudo ss -tlnp | grep 11435
   ```
2. Either:
   - Stop the conflicting service, or
   - Change the port in `/etc/hailo/hailo-vision.yaml`:
     ```yaml
     server:
       port: 11436
     ```
   - Re-run the installer:
     ```bash
     sudo ./install.sh
     sudo systemctl restart hailo-vision.service
     ```

---

### Runtime Issues

#### 5. Service crashes immediately after start
**Error:** `journalctl -u hailo-vision.service` shows: `Segmentation fault` or `Aborted`

**Cause:** Model loading failure or device issue.

**Solution:**
1. Check full logs:
   ```bash
   sudo journalctl -u hailo-vision.service -n 50 --no-pager
   ```
2. Verify device is functional:
   ```bash
   hailortcli fw-control identify
   ```
3. Check system memory (may need to close other apps):
   ```bash
   free -h
   # If memory < 2GB free, close other services
   ```
4. Restart service with verbose logging:
   ```bash
   sudo systemctl restart hailo-vision.service
   sudo journalctl -u hailo-vision.service -f
   ```

---

#### 6. "Model not found" or "Device unavailable"
**Error:** Response: `{"error": "Model not found"}` or `503 Service Unavailable`

**Cause:** Model failed to load or device is busy.

**Solution:**
1. Check service status:
   ```bash
   sudo systemctl status hailo-vision.service
   ```
2. If service is running, wait a few seconds (model may still be loading):
   ```bash
   sleep 2
   curl http://localhost:11435/health
   ```
3. If service crashed, restart:
   ```bash
   sudo systemctl restart hailo-vision.service
   sudo journalctl -u hailo-vision.service -f  # Monitor logs
   ```
4. If device is busy (another service hogging it), restart both services:
   ```bash
   sudo systemctl restart hailo-ollama.service hailo-vision.service
   ```

---

#### 7. Very slow inference (>2 seconds per image)
**Cause:** Thermal throttling, CPU contention, or device congestion.

**Solution:**
1. Check system temperature:
   ```bash
   vcgencmd measure_temp
   # If > 80°C, thermal throttling is active
   ```
2. Reduce CPU quota in `/etc/hailo/hailo-vision.yaml`:
   ```yaml
   resource_limits:
     cpu_quota: "60%"  # Lower to ease throttling
   ```
3. Check concurrent service load:
   ```bash
   ps aux | grep hailo
   free -h
   ```
4. If running multiple services, close non-essential ones:
   ```bash
   sudo systemctl stop hailo-ollama.service  # Temporarily
   # Test vision service performance
   sudo systemctl start hailo-ollama.service
   ```

---

#### 8. Out of Memory (OOM) errors
**Error:** Service crashes with `Out of memory` in logs, or systemd-oomkill kills service.

**Cause:** Model + concurrent services exceeding available RAM.

**Solution:**
1. Check memory usage:
   ```bash
   free -h
   ps aux | grep hailo
   ```
2. If using hailo-ollama + hailo-vision together:
   - Adjust MemoryMax for one or both services
   - Edit `/etc/systemd/system/hailo-vision.service.d/override.conf`:
     ```ini
     [Service]
     MemoryMax=3G
     ```
   - Reload and restart:
     ```bash
     sudo systemctl daemon-reload
     sudo systemctl restart hailo-vision.service
     ```
3. Or reduce model memory footprint:
   - Reduce max_tokens in config.yaml
   - Use lighter model variant (if available)

---

### API Issues

#### 9. 400 Bad Request: "Image resolution exceeds maximum"
**Error:** `{"error": {"message": "Image resolution exceeds maximum (8640x4320)"}}`

**Cause:** Image is too large (> 8 MP).

**Solution:**
1. Resize image before sending:
   ```bash
   # Using ImageMagick
   convert large_image.jpg -resize 3000x2000 resized_image.jpg
   ```
2. Or use the following Python snippet:
   ```python
   from PIL import Image
   
   img = Image.open("large_image.jpg")
   img.thumbnail((3000, 2000))
   img.save("resized.jpg")
   ```

---

#### 10. 413 Payload Too Large
**Error:** `413 Payload Too Large`

**Cause:** Request body exceeds size limit (~10 MB).

**Solution:**
1. Compress images before sending:
   ```bash
   convert image.jpg -quality 85 compressed.jpg
   ```
2. Or use base64 instead of keeping very large payloads:
   - Keep request bodies under 10 MB
   - Consider sending multiple smaller requests

---

#### 11. Streaming response doesn't work (stream=true returns 400)
**Error:** `POST /v1/chat/completions` with `"stream": true` returns error or hangs.

**Cause:** Streaming support may be experimental; may not be fully implemented.

**Solution:**
1. Use `stream=false` for now:
   ```bash
   curl -X POST http://localhost:11435/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "qwen2-vl-2b-instruct", "messages": [...], "stream": false}'
   ```
2. For streaming support, file an issue or wait for future updates.

---

### Configuration & Logging

#### 12. Changes to config.yaml don't take effect
**Cause:** Service is still running old config.

**Solution:**
1. After editing `/etc/hailo/hailo-vision.yaml`, restart the service:
   ```bash
   sudo systemctl restart hailo-vision.service
   ```
2. Verify changes took effect:
   ```bash
   sudo curl http://localhost:11435/health
   ```

---

#### 13. Can't find service logs
**Solution:**
```bash
# View real-time logs
sudo journalctl -u hailo-vision.service -f

# View all logs (latest first)
sudo journalctl -u hailo-vision.service --reverse

# Last 100 lines
sudo journalctl -u hailo-vision.service -n 100

# Only errors
sudo journalctl -u hailo-vision.service -p err

# Last hour
sudo journalctl -u hailo-vision.service --since "1 hour ago"
```

---

### Verification Steps

#### Quick Health Check
```bash
# 1. Service running?
sudo systemctl status hailo-vision.service

# 2. Port accessible?
curl http://localhost:11435/health

# 3. Model loaded?
curl http://localhost:11435/health | jq '.model_loaded'

# 4. Memory usage?
ps aux | grep hailo-vision

# 5. Can process images?
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    "stream": false
  }'
```

---

## Recovery Procedures

### Full Service Reset
```bash
# 1. Stop service
sudo systemctl stop hailo-vision.service

# 2. Clear state (if corrupted)
sudo rm -rf /var/lib/hailo-vision/*
sudo mkdir -p /var/lib/hailo-vision

# 3. Reset permissions
sudo chown -R hailo-vision:hailo-vision /var/lib/hailo-vision

# 4. Restart
sudo systemctl start hailo-vision.service
sudo journalctl -u hailo-vision.service -f
```

### Reinstall Service
```bash
# 1. Uninstall
sudo ./uninstall.sh --purge-data

# 2. Reinstall
sudo ./install.sh

# 3. Verify
sudo ./verify.sh
```

---

## Support & Debugging

For detailed logs, run:
```bash
sudo journalctl -u hailo-vision.service --all -o verbose -n 200
```

Include this output when reporting issues.
