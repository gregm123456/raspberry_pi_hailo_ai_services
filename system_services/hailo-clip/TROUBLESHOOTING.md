# Hailo CLIP Service - Troubleshooting Guide

## Common Issues and Solutions

### Service Won't Start

#### Symptom
```bash
sudo systemctl status hailo-clip.service
# Result: failed (red) or activating indefinitely
```

**Causes and Solutions:**

1. **Hailo device not found**
   ```bash
   # Check device exists
   ls -la /dev/hailo0
   # Should output: crw-rw---- 1 root hailo-group ...
   
   # Fix: Install Hailo driver
   sudo apt install dkms hailo-h10-all
   sudo reboot
   ```

2. **hailo-clip user missing device group membership**
   ```bash
   # Check groups
   id hailo-clip
   # Should include a hailo GPU group
   
   # Re-run installer to fix
   sudo ./install.sh
   ```

3. **Port already in use**
   ```bash
   # Check port 5000
   sudo ss -lnt | grep 5000
   
   # Solution: Change port in /etc/hailo/hailo-clip.yaml
   sudo nano /etc/hailo/hailo-clip.yaml
   # Edit server.port: 5001 (or another available port)
   sudo systemctl restart hailo-clip.service
   ```

4. **Python dependencies missing**
   ```bash
   # Check logs
   sudo journalctl -u hailo-clip.service -n 50 --no-pager
   
   # Install missing packages
   sudo apt install python3-yaml python3-numpy python3-pil
   pip3 install flask opencv-python
   ```

5. **hailo-apps CLIP module not available**
   ```bash
   # Verify hailo-apps is initialized in the vendor directory
   ls -la /opt/hailo-clip/vendor/hailo-apps/hailo_apps/python/pipeline_apps/clip/
   
   # If missing, ensure it exists in the main repo and re-run installer
   git submodule update --init --recursive
   sudo ./install.sh
   ```

**Check detailed logs:**
```bash
sudo journalctl -u hailo-clip.service -f
# Look for ERROR lines indicating the root cause
```

---

### Service Crashes Repeatedly

#### Symptom
```bash
sudo journalctl -u hailo-clip.service
# Result: Many restarts with "Restart=always"
```

**Causes and Solutions:**

1. **Out of memory**
   ```bash
   # Check system memory
   free -h
   
   # Monitor service memory usage
   systemd-cgtop
   # Look for "hailo-clip" row; if approaching 3GB, that's the issue
   
   # Solutions:
   # - Stop other services
   # - Increase MemoryMax in /etc/systemd/system/hailo-clip.service
   #   (not recommended; better to reduce other services)
   ```

2. **Model loading timeout**
   ```bash
   # First request takes very long (>120s)
   # Check if model is large or hailo-apps is slow to import
   
   # Increase timeout in systemd unit:
   sudo systemctl edit hailo-clip.service
   # Add under [Service]:
   # TimeoutStartSec=300
   ```

3. **Hailo device contention**
   ```bash
   # Multiple services using /dev/hailo0 simultaneously
   # Check running services
   systemctl list-units --type=service | grep hailo
   
   # Solution: Stop conflicting services or use device concurrency features
   ```

---

### Health Check Fails

#### Symptom
```bash
curl http://localhost:5000/health
# Result: curl: (7) Failed to connect to port 5000: Connection refused
```

**Diagnosis:**

1. **Service not running**
   ```bash
   sudo systemctl status hailo-clip.service
   # Should show: active (running)
   
   # If not running, check logs
   sudo journalctl -u hailo-clip.service -n 100 --no-pager
   ```

2. **Service running but port not listening**
   ```bash
   # Check if port 5000 is actually bound
   sudo ss -lnt | grep 5000
   
   # If not shown, Flask didn't start properly
   # Check service logs for Python errors
   sudo journalctl -u hailo-clip.service -f
   ```

3. **Port changed in config**
   ```bash
   # Verify configured port
   grep port /etc/hailo/hailo-clip.yaml
   
   # If changed, use the new port
   curl http://localhost:5001/health  # if port: 5001
   ```

**Fix:**
```bash
# Restart service with verbose logging
sudo systemctl restart hailo-clip.service
sleep 5  # Wait for startup
sudo journalctl -u hailo-clip.service -n 50 --no-pager
```

---

### Classification Requests Slow or Timeout

#### Symptom
```bash
curl -X POST http://localhost:5000/v1/classify \
  -H "Content-Type: application/json" \
  -d '{"image": "...", "prompts": ["...", "..."]}'
# Takes >10 seconds or times out
```

**Causes and Solutions:**

1. **Model still loading (first request after startup)**
   ```bash
   # This is normal for first request (can take 5-30 seconds depending on model size)
   # Subsequent requests are faster (50-150ms typical)
   
   # Use install --warmup to pre-load model
   sudo ./install.sh --warmup
   ```

2. **Too many concurrent requests**
   ```bash
   # Service queue is full
   # Check systemd unit and config:
   grep -E "worker_threads|max_queue_size" /etc/hailo/hailo-clip.yaml
   
   # Increase worker threads:
   sudo nano /etc/hailo/hailo-clip.yaml
   # Edit: performance.worker_threads: 4  (increase from 2)
   sudo systemctl restart hailo-clip.service
   ```

3. **Large image or many prompts**
   ```bash
   # Image should be reasonably sized
   # Number of prompts affects latency linearly
   
   # Example latencies:
   # - 1 prompt: ~50ms
   # - 5 prompts: ~100ms
   # - 20 prompts: ~300ms
   
   # Optimize: Use top_k to limit comparisons
   # {"prompts": [...50 items...], "top_k": 3}
   ```

4. **CPU throttling (thermal)**
   ```bash
   # Check CPU temperature
   vcgencmd measure_temp
   
   # If >>60°C, CPU is thermal throttling
   # Solutions:
   # - Reduce concurrent services
   # - Improve cooling (fan)
   # - Reduce CPUQuota in systemd unit
   ```

---

### Port Conflict

#### Symptom
```bash
sudo systemctl status hailo-clip.service
# Result: failed to bind port 5000
```

**Solution:**

1. **Find what's using port 5000**
   ```bash
   sudo lsof -i :5000
   # or
   sudo ss -ltnp | grep 5000
   ```

2. **Change CLIP port**
   ```bash
   sudo nano /etc/hailo/hailo-clip.yaml
   # Edit: server.port: 5001  (or any available port)
   
   sudo systemctl restart hailo-clip.service
   ```

---

### Classification Results Inaccurate or Unexpected

#### Symptom
```bash
# Image of person in red shirt classified as "person in blue shirt"
# OR scores are very close for all prompts (no clear winner)
```

**Causes and Solutions:**

1. **Prompts too similar**
   ```bash
   # If prompts are very similar, CLIP may struggle
   # Example: "person", "human", "individual" all similar
   
   # Better: Use distinct, descriptive prompts
   # Good: "person wearing red shirt", "person on bicycle", "empty street"
   ```

2. **Model limitations**
   ```bash
   # CLIP works best with descriptive, concrete prompts
   # Avoid: Very abstract or negation-heavy prompts
   
   # CLIP strengths:
   # ✓ Object detection: "car", "bicycle", "person"
   # ✓ Attributes: "red", "large", "moving"
   # ✓ Scenes: "outdoor", "indoor", "crowded"
   
   # CLIP weaknesses:
   # ✗ Counting: "exactly 3 people"
   # ✗ Complex reasoning: "is anyone doing something dangerous?"
   # ✗ Negation: "not a person" (use positive class instead)
   ```

3. **Image quality issues**
   ```bash
   # Blurry, very small, or heavily distorted images may confuse CLIP
   
   # Test with clear, well-lit image first
   # Verify image is correctly encoded (not corrupted base64)
   ```

4. **Threshold too high or too low**
   ```bash
   # If threshold: 0.9, only very confident matches pass
   # If threshold: 0.1, almost all matches pass
   
   # Typical range: 0.3-0.7 depending on use case
   # Example:
   # {"prompts": [...], "threshold": 0.5, "top_k": 3}
   ```

---

### Memory Usage High

#### Symptom
```bash
systemd-cgtop | grep hailo-clip
# Shows 2.5 GB or higher (approaching 3 GB limit)
```

**Causes and Solutions:**

1. **CLIP model is large**
   ```bash
   # ResNet-50x4 model ~1-2 GB
   # Flask/Python runtime ~100-200 MB
   # Total near 3 GB is expected
   
   # Check if multiple model instances loaded
   ps aux | grep hailo_clip_service.py
   # Should show exactly one process
   
   # If multiple: Kill extras and restart
   sudo systemctl restart hailo-clip.service
   ```

2. **Request accumulation**
   ```bash
   # Large image buffers or incomplete request cleanup
   
   # Solution: Restart service periodically
   # Add to crontab:
   # 0 3 * * * systemctl restart hailo-clip.service
   ```

3. **Running with other services**
   ```bash
   # Total system memory pressure
   
   # Check all hailo services
   systemctl list-units --type=service | grep hailo
   systemd-cgtop | grep hailo
   
   # If multiple services near limits, stop one or add RAM if possible
   ```

---

### Logs Show Python Errors

#### Symptom
```bash
sudo journalctl -u hailo-clip.service
# Result: Traceback, ImportError, or AttributeError
```

**Solutions:**

1. **ImportError: hailo-apps module**
   ```bash
   # Fix: ensure hailo-apps exists in the repo (installer vendors it into /opt)
   git submodule update --init --recursive

   # Reinstall service (copies hailo-apps into /opt/hailo-clip/vendor/hailo-apps)
   sudo ./install.sh

   # Smoke test import as the service user
   sudo -u hailo-clip /opt/hailo-clip/venv/bin/python3 -c "import hailo_apps.python.pipeline_apps.clip.clip; print('OK')"
   ```

2. **ImportError: Flask or other dependencies**
   ```bash
   # Install missing Python package
   pip3 install flask
   pip3 install opencv-python
   
   # Restart service
   sudo systemctl restart hailo-clip.service
   ```

3. **AttributeError: Model missing method**
   ```bash
   # hailo-apps API may have changed
   
   # Check available methods
   python3 -c "from hailo_apps.python.pipeline_apps.clip import CLIP; help(CLIP)"
   
   # Update service code if needed
   ```

---

## Verification Checklist

```bash
# 1. Device present
ls -a /dev/hailo0
# Expected: Device file exists with group membership

# 2. Service running
sudo systemctl status hailo-clip.service
# Expected: active (running)

# 3. Port listening
sudo ss -ltn | grep 5000
# Expected: LISTEN socket on 0.0.0.0:5000

# 4. Health check
curl http://localhost:5000/health
# Expected: {"status": "healthy", ...}

# 5. Classification works
curl -X POST http://localhost:5000/v1/classify \
  -H "Content-Type: application/json" \
  -d '{"image": "data:image/jpeg;base64,...", "prompts": ["test"]}'
# Expected: 200 OK with classifications

# 6. Memory reasonable
systemd-cgtop | grep hailo-clip
# Expected: <3GB (near limit is OK, exactly at limit is problem)

# 7. Logs clean
sudo journalctl -u hailo-clip.service --no-pager | tail -20
# Expected: No ERROR lines; INFO messages showing requests
```

---

## Support & Contact

For persistent issues:

1. Collect diagnostics:
   ```bash
   sudo journalctl -u hailo-clip.service -n 200 > hailo-clip-logs.txt
   cat /etc/hailo/hailo-clip.yaml > hailo-clip-config.txt
   systemctl status hailo-clip.service > hailo-clip-status.txt
   ```

2. Check [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md)

3. Review [API_SPEC.md](API_SPEC.md) for endpoint reference
