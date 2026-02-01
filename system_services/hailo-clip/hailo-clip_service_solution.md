# Hailo CLIP Service Solution - Technical Documentation

This document outlines the architecture, implementation, and deployment of the Hailo-accelerated CLIP (Contrastive Language-Image Pre-training) service for the Raspberry Pi 5 with Hailo-10H NPU.

## 1. Overview

The `hailo-clip` service provides a RESTful API for Zero-Shot Image Classification. It leverages the Hailo-10H NPU to perform high-speed inference on both image and text encoders, allowing users to classify images against arbitrary text prompts without retraining.

### Architecture Highlights:
- **Models**: MobileCLIP / CLIP ViT-B/32 (Optimized for Hailo-10H).
- **Backend**: Flask-based REST API.
- **Acceleration**: HailoRT with dual-model single-VDevice scheduling.
- **Deployment**: Managed systemd service running as an isolated user.

---

## 2. Technical Challenges & Solutions

### 2.1 Hardware Resource Contention (Single VDevice)
**Problem**: The Raspberry Pi 5 with AI HAT+ (Hailo-10H) has a single physical NPU device. Many CLIP implementations initialize the image and text encoders separately, creating multiple `VDevice` handles. This leads to `HAILO_OUT_OF_PHYSICAL_DEVICES (74)` errors.

**Solution**: The service was refactored to manage a single shared `VDevice`. Both the Image and Text `InferenceModel` objects are created from the same device instance, and were switched to use `HailoSchedulingAlgorithm.ROUND_ROBIN` (via `VDevice.create_params()`).

### 2.2 Path & Permission Isolation
**Problem**: Initial versions depended on file paths within the `/home/gregm` user directory, which is inaccessible to system services and breaks deployment on other machines.

**Solution**:
- **Deployment Root**: Moved all service code and virtual environments to `/opt/hailo-clip/`.
- **User Separation**: Created a dedicated `hailo-clip` system user with restricted permissions.
- **Vendoring**: Pertinent utilities from the `hailo-apps` submodule were vendored into the deployment directory to ensure zero external dependencies on user-land code.

### 2.3 Resource Management
**Problem**: Large HEF files and support assets (tokenizer, projection matrices) were missing or inconsistently located.

**Solution**: The [install.sh](install.sh) was updated to automatically pull verified resources from the Hailo S3 bucket.
- **Models**: `/usr/local/hailo/resources/models/hailo10h/`
- **Support Files**: Tokenizer and NPY files in `/usr/local/hailo/resources/configs/` and `/usr/local/hailo/resources/npy/`.

---

## 3. Service Implementation

### 3.1 Advanced Post-Processing
To provide user-friendly classification scores, the service implements a numerically stable **Scaled Softmax**:

$$
\text{score}_i = \frac{e^{\tau \cdot (s_i - \max(s))}}{\sum_j e^{\tau \cdot (s_j - \max(s))}}
$$

Where $\tau$ is the `logit_scale` (default 100.0) and $s$ are the raw cosine similarities. This transforms small differences in similarity (e.g., 0.26 vs 0.21) into meaningful probabilities (e.g., 0.99 vs 0.005).

---

## 4. Deployment Structure

The system is organized as follows:

- `/etc/hailo/hailo-clip.yaml`: Service configuration (Host, Port, Logit Scale).
- `/etc/systemd/system/hailo-clip.service`: Systemd unit file.
- `/opt/hailo-clip/`:
    - `venv/`: Isolated Python environment.
    - `hailo_clip_service.py`: Core service logic.
    - `hailo_apps/`: Vendored support library.
- `/var/lib/hailo-clip/`: State directory for logs and temporary files.

---

## 5. API Usage

### Classification Endpoint
`POST /v1/classify`

**Request Body:**
```json
{
  "image": "data:image/jpeg;base64,...",
  "prompts": ["a cat", "a dog", "a car"],
  "top_k": 3,
  "threshold": 0.0
}
```

**Successful Response:**
```json
{
  "classifications": [
    { "rank": 1, "score": 0.9909, "text": "a cat" },
    { "rank": 2, "score": 0.0056, "text": "a dog" },
    { "rank": 3, "score": 0.0018, "text": "a car" }
  ],
  "inference_time_ms": 177.3,
  "model": "clip-vit-b-32"
}
```

---

## 6. Verification & Troubleshooting

### Status Check
```bash
sudo systemctl status hailo-clip
```

### Log Inspection
```bash
journalctl -u hailo-clip -f
```

### Resource Verification
Ensure HEF files are present:
```bash
hailortcli fw-control identify
ls /usr/local/hailo/resources/models/hailo10h/
```
