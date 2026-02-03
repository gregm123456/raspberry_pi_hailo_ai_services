# Troubleshooting — hailo-ocr

Common issues and quick fixes.

- Service won't start / systemd errors
  - Check unit status: `sudo systemctl status hailo-ocr` and logs: `sudo journalctl -u hailo-ocr -n 200 -f`.
  - Ensure `/dev/hailo0` exists and service user is in `hailo` group.

- Model download / permission errors during install
  - Installer downloads HEF files to `/var/lib/hailo-ocr/resources/` — run installer with sudo and ensure directory ownership: `sudo chown -R hailo-ocr:hailo-ocr /var/lib/hailo-ocr`.

- Detection misses text or returns wrong boxes
  - The server letterboxes (resizes with padding) to the model input. Do not pre-stretch images.
  - For thin or low-contrast text, increase input image resolution or improve contrast before sending.
  - Detection uses DBNet with a binarization threshold around `0.3` and an adaptive strategy; extremely sparse text may need higher resolution.

- Recognition errors (characters mis-read)
  - These are model recognition artifacts. Consider post-processing (spell-correction) or using a language-specific recognition HEF.

- Performance and memory
  - Recognition batch size defaults to 8 for throughput. Adjust `hailo_models.batch_size_rec` in `/etc/hailo/hailo-ocr.yaml` if needed.
  - MemoryMax for the systemd unit is set during installation; reduce concurrency if you run out of memory.
# Troubleshooting Hailo-10H OCR Service

This guide covers common issues with the NPU-accelerated OCR service.

## 1. Verify Service Status
Check if the service is running and view recent logs:
```bash
sudo systemctl status hailo-ocr
sudo journalctl -u hailo-ocr -f
```

## 2. NPU Connectivity Issues
If the service logs show "Hailo device not found" or "Failed to load HEF":
1. **Check Driver:** `hailortcli fw-control identify`
2. **Check PCIe:** `lspci | grep Hailo`
3. **Internal Tools:** Use `hailortcli scan` to see connected devices.

## 3. Empty Results or Poor Accuracy
If OCR returns no text or gibberish:
- **Model Check:** Ensure `ocr_det.hef` and `ocr.hef` were downloaded during installation.
- **Resizer Issues:** The service uses a two-stage pipeline. If detection fails, recognition is never triggered. Check the input image resolution; very small text might need pre-scaling.
- **Language Mismatch:** Ensure `languages: ["zh"]` is passed for Chinese text; the default English model cannot read Chinese characters.

## 4. Performance Bottlenecks
- **NPU Temperature:** High temperatures can trigger throttling. Check with `hailortcli monitor`.
- **Batch Size:** The recognition model is optimized for batching. If processing many small lines, the service waits for 8 crops (or a 50ms timeout).
- **CPU vs NPU:** While detection/recognition are on NPU, pre/post-processing (CV2 resizing, padding) happen on the CPU. High CPU load on the Pi 5 will slow down OCR.

## 5. Model Download Failures
The `install.sh` script uses `hailo-download-resources` to fetch models. If models are missing in `/opt/hailo-ocr/venv/lib/python3.11/site-packages/hailo_apps/resources/`:
1. Manually run the downloader:
   ```bash
   source /opt/hailo-ocr/venv/bin/activate
   hailo-download-resources ocr
   ```

## 6. Restarting the Service
After fixing configuration or model issues, restart:
```bash
sudo systemctl restart hailo-ocr
```
