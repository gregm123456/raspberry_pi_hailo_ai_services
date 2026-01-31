# Hailo OCR Service — Troubleshooting Guide

## Common Issues

### Service fails to start

**Error:** `systemctl status hailo-ocr.service` shows failed or inactive

**Check logs:**
```bash
sudo journalctl -u hailo-ocr.service -n 50 --no-pager
```

**Common causes:**

1. **Python dependencies missing:**
   ```bash
   python3 -m pip install paddleocr pillow aiohttp pyyaml
   ```

2. **PaddleOCR models not found:**
   ```bash
   sudo -u hailo-ocr python3 -c "from paddleocr import PaddleOCR; PaddleOCR()"
   ```
   This will download necessary models to `~hailo-ocr/.paddleocr/` (typically `/var/lib/hailo-ocr/.paddleocr/`)

3. **Permission error on `/var/lib/hailo-ocr`:**
   ```bash
   sudo chown -R hailo-ocr:hailo-ocr /var/lib/hailo-ocr
   sudo chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-ocr
   ```

4. **Port already in use:**
   ```bash
   sudo ss -lnt | grep 11436
   sudo lsof -i :11436
   # Update port in /etc/hailo/hailo-ocr.yaml and restart
   ```

### Service runs but health check fails

**Error:** `curl http://localhost:11436/health` returns connection refused or timeout

**Check process:**
```bash
ps aux | grep hailo-ocr
sudo systemctl status hailo-ocr.service
```

**Check logs for errors:**
```bash
sudo journalctl -u hailo-ocr.service -f
```

**Possible causes:**

1. **Service is loading models (first request):**
   - Wait 10-15 seconds and retry: `sleep 10 && curl http://localhost:11436/health`

2. **Memory exhaustion:**
   ```bash
   free -h
   sudo journalctl -u systemd-oomkill -n 20
   ```
   - Stop other services: `sudo systemctl stop hailo-ollama.service hailo-vision.service`

3. **Python crash:**
   ```bash
   sudo journalctl -u hailo-ocr.service -n 100 | grep -i "error\|traceback\|exception"
   ```

### High startup time

**Issue:** Health check takes >5 seconds to respond

**Causes:**

1. **Models downloading for first time:**
   - First request downloads detection + recognition models (~500 MB total)
   - Subsequent requests are fast (~200-600 ms)
   - Pre-warm: `curl -X POST http://localhost:11436/v1/ocr/extract -H "Content-Type: application/json" -d '{"image":"data:image/jpeg;base64,..."}'`

2. **Slow network (Pi 5 downloading models):**
   - Ensure Ethernet connection or 5 GHz Wi-Fi
   - Check bandwidth: `iperf3 -c server.local`

### OCR results are inaccurate

**Issue:** Text recognition confidence is low or text is missed

**Adjust thresholds:**
```bash
# Edit config
sudo nano /etc/hailo/hailo-ocr.yaml

# Change detection/recognition thresholds:
ocr:
  det_threshold: 0.2  # Lowered from 0.3 (more aggressive)
  rec_threshold: 0.3  # Lowered from 0.5

# Restart service
sudo systemctl restart hailo-ocr.service
```

**Or adjust per-request:**
```bash
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,...",
    "det_threshold": 0.2,
    "rec_threshold": 0.3
  }'
```

**Debug image quality:**
- Ensure images are well-lit, high contrast
- Typical resolution ≥1200×800 pixels
- Supported formats: JPEG, PNG, WebP, BMP
- Test with: `identify image.jpg` (from ImageMagick)

### Out of memory (OOM) errors

**Symptoms:**
- Service crashes after running for a while
- `journalctl` shows `systemd-oomkill`

**Check memory usage:**
```bash
free -h
ps aux | grep hailo | sort -k4 -nr
```

**Solutions:**

1. **Disable caching:**
   ```bash
   sudo sed -i 's/enable_caching: true/enable_caching: false/' /etc/hailo/hailo-ocr.yaml
   sudo systemctl restart hailo-ocr.service
   ```

2. **Reduce cache TTL:**
   ```bash
   sudo sed -i 's/cache_ttl_seconds: 3600/cache_ttl_seconds: 600/' /etc/hailo/hailo-ocr.yaml
   sudo systemctl restart hailo-ocr.service
   ```

3. **Stop concurrent services:**
   ```bash
   sudo systemctl stop hailo-ollama.service hailo-vision.service
   # Run as many as needed, monitoring free memory
   free -h
   ```

4. **Increase MemoryMax:**
   ```bash
   sudo systemctl edit hailo-ocr.service
   # Add or modify:
   # [Service]
   # MemoryMax=3G
   
   sudo systemctl daemon-reload
   sudo systemctl restart hailo-ocr.service
   ```

### Batch processing is slow

**Issue:** `POST /v1/ocr/batch` takes longer than expected

**Check parallel limit:**
```bash
# Current setting (grep for parallel_limit in config if exposed)
# Increase parallel processing (careful: CPU-bound)
curl -X POST http://localhost:11436/v1/ocr/batch \
  -H "Content-Type: application/json" \
  -d '{
    "images": [...],
    "parallel_limit": 2
  }'
```

**Note:** PaddleOCR is CPU-intensive; `parallel_limit > 2` usually doesn't help on Pi 5 (4-core).

### Network timeout on image download

**Error:** `GET https://example.com/image.jpg` times out

**Check network:**
```bash
ping -c 3 example.com
curl -I https://example.com/image.jpg
```

**Solution:** Use local file or base64 encoding:
```bash
# Option 1: Local file
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{"image":"file:///tmp/image.jpg"}'

# Option 2: Base64
IMAGE_B64=$(base64 -w0 < /tmp/image.jpg)
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d "{\"image\":\"data:image/jpeg;base64,$IMAGE_B64\"}"
```

### Cache not working

**Issue:** Results not being reused from cache

**Check cache stats:**
```bash
curl http://localhost:11436/cache/stats
```

**Verify caching enabled in config:**
```bash
grep enable_caching /etc/hailo/hailo-ocr.yaml
# Should be: enable_caching: true
```

**Ensure request_id or image hash matches:**
```bash
# First request with caching enabled
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image": "data:image/jpeg;base64,...",
    "cache_result": true
  }'

# Second identical request should return faster and show "cached: true"
```

### Thermal throttling

**Issue:** OCR performance degrades over time during heavy use

**Check temperature:**
```bash
vcgencmd measure_temp
# Throttle if >80°C
```

**Solutions:**

1. **Reduce CPU quota:**
   ```bash
   sudo systemctl edit hailo-ocr.service
   # [Service]
   # CPUQuota=50%  # Reduce from 75%
   ```

2. **Add passive cooling:**
   - Aluminum heatsink on Pi 5
   - Small fan directed at SoC

3. **Stagger batch jobs:**
   - Process in smaller batches with delays
   - Monitor `vcgencmd measure_temp` between batches

4. **Reduce background load:**
   ```bash
   sudo systemctl stop hailo-ollama.service hailo-vision.service
   ```

## Verification Steps

### 1. Service Status

```bash
sudo systemctl status hailo-ocr.service
```

Expected output: `active (running)`

### 2. Health Check

```bash
curl http://localhost:11436/health
```

Expected: JSON with `"status": "ok"`

### 3. Basic OCR

```bash
# Create a simple test image (white square with black text "TEST")
python3 << 'PY'
from PIL import Image, ImageDraw
img = Image.new('RGB', (200, 100), color='white')
d = ImageDraw.Draw(img)
d.text((50, 40), "TEST", fill='black')
img.save('/tmp/test.jpg')
PY

# Encode and send
IMG_B64=$(base64 -w0 < /tmp/test.jpg)
curl -X POST http://localhost:11436/v1/ocr/extract \
  -H "Content-Type: application/json" \
  -d "{\"image\":\"data:image/jpeg;base64,$IMG_B64\",\"languages\":[\"en\"]}"
```

Expected: JSON with recognized text "TEST" in `text` field

### 4. Resource Usage

```bash
ps aux | grep hailo-ocr | grep -v grep
# Check RSS (resident set size) — should be ~1.5-2.5 GB

free -h
# Available memory should be reasonable

vcgencmd measure_temp
# Temperature should be <75°C under load
```

### 5. Concurrent Operation

```bash
# Check running services
sudo systemctl list-units --type=service --state=running | grep hailo

# Monitor memory
watch -n 1 'free -h && echo "---" && ps aux | grep hailo | grep -v grep'
```

## Advanced Debugging

### Enable verbose logging

```bash
# Edit service to add debug environment
sudo systemctl edit hailo-ocr.service
# Add:
# [Service]
# Environment=PADDLEOCR_DEBUG=1

sudo systemctl daemon-reload
sudo systemctl restart hailo-ocr.service
sudo journalctl -u hailo-ocr.service -f
```

### Test with Python directly

```bash
sudo -u hailo-ocr python3 << 'PY'
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_gpu=False, lang=['en'])
result = ocr.ocr('/path/to/image.jpg')
for line in result:
    for word_info in line:
        print(word_info)
PY
```

### Check model files

```bash
ls -lh /var/lib/hailo-ocr/.paddleocr/
# Should contain detection and recognition model files
du -sh /var/lib/hailo-ocr/.paddleocr/
# Typical size: 500-800 MB
```

### Monitor service process

```bash
# Real-time CPU/memory
top -p $(pgrep -f hailo-ocr) -b -n 1

# Network connections (if using remote images)
netstat -tp | grep hailo-ocr

# File descriptors
ls -la /proc/$(pgrep -f hailo-ocr)/fd/ | wc -l
```

## Getting Help

1. **Check logs first:**
   ```bash
   sudo journalctl -u hailo-ocr.service -n 200 --no-pager
   ```

2. **Run verification:**
   ```bash
   sudo ./verify.sh
   ```

3. **Test health:**
   ```bash
   curl http://localhost:11436/health
   curl http://localhost:11436/models
   ```

4. **Inspect configuration:**
   ```bash
   cat /etc/hailo/hailo-ocr.yaml
   cat /etc/xdg/hailo-ocr/hailo-ocr.json
   ```

5. **Review API spec:** [API_SPEC.md](API_SPEC.md)

6. **Check architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
