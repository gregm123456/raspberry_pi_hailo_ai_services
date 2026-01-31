# Hailo Face Recognition Service Troubleshooting

Common issues and solutions for hailo-face service.

## Table of Contents

- [Service Won't Start](#service-wont-start)
- [Health Check Fails](#health-check-fails)
- [Model Loading Errors](#model-loading-errors)
- [Database Errors](#database-errors)
- [Inference Failures](#inference-failures)
- [Performance Issues](#performance-issues)
- [Memory Issues](#memory-issues)
- [Device Access Errors](#device-access-errors)

---

## Service Won't Start

### Symptom
```bash
sudo systemctl status hailo-face
● hailo-face.service - Hailo Face Recognition
     Loaded: loaded
     Active: failed (Result: exit-code)
```

### Check 1: View Logs
```bash
sudo journalctl -u hailo-face -n 50 --no-pager
```

Look for error messages indicating the root cause.

### Check 2: Verify Hailo Driver
```bash
lsmod | grep hailo
```

**Expected:** `hailo_pci` module loaded

**Fix if missing:**
```bash
sudo apt install dkms hailo-h10-all
sudo reboot
```

### Check 3: Check Python Dependencies
```bash
python3 -c "import flask, yaml, cv2, PIL, numpy"
```

**Fix if import fails:**
```bash
python3 -m pip install --break-system-packages flask pyyaml opencv-python pillow numpy
```

### Check 4: Verify User Permissions
```bash
id hailo-face
```

**Expected:** User exists and is in `video` group

**Fix:**
```bash
sudo usermod -a -G video hailo-face
sudo systemctl restart hailo-face
```

### Check 5: Configuration File
```bash
cat /etc/hailo/hailo-face.yaml
```

**Verify:**
- File exists and is readable
- YAML syntax is valid
- Paths are correct

**Fix:**
```bash
cd /path/to/system_services/hailo-face
sudo ./install.sh  # Reinstall
```

---

## Health Check Fails

### Symptom
```bash
curl http://localhost:5002/health
curl: (7) Failed to connect to localhost port 5002
```

### Check 1: Service Running
```bash
sudo systemctl is-active hailo-face
```

**Fix if inactive:**
```bash
sudo systemctl start hailo-face
```

### Check 2: Port Binding
```bash
sudo ss -tulpn | grep 5002
```

**Expected:** Process listening on port 5002

**Fix if different port:**
Edit `/etc/hailo/hailo-face.yaml`:
```yaml
server:
  port: 5002  # Or your desired port
```

Then restart:
```bash
sudo systemctl restart hailo-face
```

### Check 3: Firewall
```bash
sudo iptables -L | grep 5002
```

**Fix if blocked:**
```bash
sudo iptables -A INPUT -p tcp --dport 5002 -j ACCEPT
```

---

## Model Loading Errors

### Symptom
```
ERROR - Failed to load face models
ERROR - Model file not found
```

### Check 1: Mock Mode Active
```bash
sudo journalctl -u hailo-face | grep -i "mock"
```

**If using mock mode:**
This is expected behavior when hailo-apps integration is not yet complete. The service runs with simulated inference.

**To verify mock mode:**
```bash
curl http://localhost:5002/health | python3 -m json.tool
```

Look for `"model_loaded": true` (even in mock mode).

### Check 2: hailo-apps Installation
```bash
python3 -c "from hailo_apps.python.pipeline_apps.face_recognition.face_recognition import CLIP"
```

**Fix if ImportError:**
```bash
cd /path/to/hailo-apps
./install.sh
```

### Check 3: Model Files Present
```bash
ls /usr/share/hailo-models/ | grep -E "scrfd|arcface"
```

**Fix if missing:**
```bash
# Download models from Hailo Model Zoo
# Or install via hailo-apps
```

---

## Database Errors

### Symptom
```
ERROR - Failed to initialize database
ERROR - Database locked
```

### Check 1: Database File Permissions
```bash
ls -l /var/lib/hailo-face/faces.db
```

**Expected:** Owned by `hailo-face:hailo-face` with read/write

**Fix:**
```bash
sudo chown hailo-face:hailo-face /var/lib/hailo-face/faces.db
sudo chmod 644 /var/lib/hailo-face/faces.db
```

### Check 2: Directory Permissions
```bash
ls -ld /var/lib/hailo-face/
```

**Expected:** `drwxr-xr-x hailo-face hailo-face`

**Fix:**
```bash
sudo chown -R hailo-face:hailo-face /var/lib/hailo-face/
sudo chmod 755 /var/lib/hailo-face/
```

### Check 3: Database Corruption
```bash
sqlite3 /var/lib/hailo-face/faces.db "PRAGMA integrity_check;"
```

**Expected:** `ok`

**Fix if corrupted:**
```bash
# Backup current database
sudo cp /var/lib/hailo-face/faces.db /var/lib/hailo-face/faces.db.corrupt

# Reinitialize
sudo rm /var/lib/hailo-face/faces.db
sudo systemctl restart hailo-face

# Or restore from backup if available
sudo cp /var/lib/hailo-face/backups/faces.db.backup /var/lib/hailo-face/faces.db
sudo chown hailo-face:hailo-face /var/lib/hailo-face/faces.db
sudo systemctl restart hailo-face
```

### Check 4: Disk Space
```bash
df -h /var/lib/hailo-face/
```

**Fix if full:**
```bash
# Clean old backups
sudo rm /var/lib/hailo-face/backups/*.old
```

---

## Inference Failures

### Symptom
```
POST /v1/detect returns 500 error
"error": "Failed to detect faces"
```

### Check 1: Image Format
**Valid formats:** JPEG, PNG, BMP, WebP  
**Encoding:** Base64 with optional data URI prefix

**Test with valid image:**
```bash
curl -X POST http://localhost:5002/v1/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\":\"$(base64 -w0 test.jpg | sed 's/^/data:image\/jpeg;base64,/')\"}"
```

### Check 2: Image Size
**Recommended:** <5MB compressed, <4096x4096 pixels

**Test smaller image:**
```bash
convert large_image.jpg -resize 1920x1080 test_small.jpg
```

### Check 3: Device Timeout
```bash
sudo journalctl -u hailo-face | grep -i timeout
```

**Fix if device timeout:**
Edit `/etc/hailo/hailo-face.yaml`:
```yaml
face_recognition:
  device_timeout_ms: 10000  # Increase to 10 seconds
```

Then restart:
```bash
sudo systemctl restart hailo-face
```

### Check 4: Concurrent Requests
Too many concurrent requests can cause queue overflow.

**Fix:**
Edit `/etc/hailo/hailo-face.yaml`:
```yaml
performance:
  max_queue_size: 20  # Increase queue
  request_timeout: 60  # Longer timeout
```

---

## Performance Issues

### Symptom: Slow Inference

**Expected latencies:**
- Detection: 30-50ms
- Embedding: 20-40ms
- Recognition: 50-150ms

### Check 1: System Load
```bash
htop
```

Look for:
- CPU usage >90%
- Memory usage >80%
- Thermal throttling warnings

**Fix:**
```bash
# Reduce concurrent services
sudo systemctl stop hailo-vision
sudo systemctl stop hailo-clip

# Or adjust CPU quota
sudo systemctl edit hailo-face
# Add:
[Service]
CPUQuota=50%
```

### Check 2: Device Utilization
```bash
hailortcli run /usr/share/hailo-models/scrfd_10g.hef
```

**Expected:** Inference completes without errors

### Check 3: Database Size
```bash
sqlite3 /var/lib/hailo-face/faces.db "SELECT COUNT(*) FROM embeddings;"
```

**Large databases (>1000 embeddings) slow down matching.**

**Optimize:**
```python
# TODO: Implement FAISS indexing for large databases
# Current linear scan: O(n) complexity
```

---

## Memory Issues

### Symptom: Service Crashes or OOM

```bash
sudo journalctl -u hailo-face | grep -i "killed\|oom"
```

### Check 1: Memory Limit
```bash
systemctl show hailo-face | grep MemoryMax
```

**Expected:** `MemoryMax=3221225472` (3GB)

**Adjust if needed:**
```bash
sudo systemctl edit hailo-face
# Add:
[Service]
MemoryMax=4G
```

### Check 2: Total System Memory
```bash
free -h
```

**Raspberry Pi 5:** ~5.8GB available after OS

**Fix if running out:**
```bash
# Stop other services
sudo systemctl stop hailo-ollama
sudo systemctl stop hailo-florence

# Or reduce service memory
sudo systemctl edit hailo-face
[Service]
MemoryMax=2G
```

### Check 3: Memory Leaks
```bash
# Monitor over time
watch -n 5 'systemctl status hailo-face | grep Memory'
```

**If memory grows continuously:**
- Restart service periodically
- File a bug report with logs

---

## Device Access Errors

### Symptom
```
ERROR - Failed to open Hailo device
ERROR - Permission denied: /dev/hailo0
```

### Check 1: Device Exists
```bash
ls -l /dev/hailo*
```

**Expected:** `/dev/hailo0` with `video` group

**Fix if missing:**
```bash
sudo modprobe hailo_pci
```

### Check 2: User in Video Group
```bash
id hailo-face | grep video
```

**Fix if not in video group:**
```bash
sudo usermod -a -G video hailo-face
sudo systemctl restart hailo-face
```

### Check 3: Device In Use
```bash
lsof | grep hailo
```

**If multiple services using device:**
Hailo-10H supports concurrent access, but check resource contention.

### Check 4: Driver Version
```bash
hailortcli fw-control identify
```

**Expected:** Firmware version displayed

**Fix if error:**
```bash
sudo apt update
sudo apt install --reinstall hailo-h10-all
sudo reboot
```

---

## Common Configuration Mistakes

### Wrong Port in Config
```yaml
server:
  port: 5002  # Must match your client requests
```

### Threshold Too High
```yaml
face_recognition:
  recognition_threshold: 0.5  # Lower for more lenient matching
  detection_threshold: 0.6    # Lower to detect more faces
```

### Database Disabled
```yaml
database:
  enabled: true  # Must be true for recognition
```

---

## Debugging Commands

### Full Service Status
```bash
sudo systemctl status hailo-face --full --no-pager
```

### Live Logs
```bash
sudo journalctl -u hailo-face -f
```

### Test API Manually
```bash
# Health
curl http://localhost:5002/health | python3 -m json.tool

# List identities
curl http://localhost:5002/v1/database/list | python3 -m json.tool

# Detect faces (need actual image)
curl -X POST http://localhost:5002/v1/detect \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

### Check Resource Usage
```bash
# Memory
systemctl status hailo-face | grep Memory

# CPU
top -p $(pgrep -f hailo_face_service.py)

# Disk
du -sh /var/lib/hailo-face/
```

---

## Getting Help

### Gather Debug Info

```bash
# Create debug report
{
  echo "=== Service Status ==="
  sudo systemctl status hailo-face --no-pager
  
  echo -e "\n=== Recent Logs ==="
  sudo journalctl -u hailo-face -n 100 --no-pager
  
  echo -e "\n=== Configuration ==="
  cat /etc/hailo/hailo-face.yaml
  
  echo -e "\n=== System Info ==="
  uname -a
  free -h
  df -h /var/lib/hailo-face
  
  echo -e "\n=== Hailo Device ==="
  hailortcli fw-control identify
  
} > hailo-face-debug.txt
```

Send `hailo-face-debug.txt` when reporting issues.

### Additional Resources

- **Hailo Documentation:** https://hailo.ai/developer-zone/
- **hailo-apps Repository:** GitHub issues and examples
- **System Setup Guide:** `reference_documentation/system_setup.md`

---

## Reset Service to Defaults

If all else fails:

```bash
# Uninstall completely
cd /path/to/system_services/hailo-face
sudo ./uninstall.sh

# Delete ALL data (including database)
sudo rm -rf /var/lib/hailo-face
sudo rm -rf /etc/hailo/hailo-face.yaml

# Reinstall fresh
sudo ./install.sh

# Verify
./verify.sh
```

---

**Last Updated:** 2026-01-31  
**Version:** 1.0.0
