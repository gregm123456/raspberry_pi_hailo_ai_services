# Model Acquisition & Installation Guide

## Overview

This guide explains how the hailo-depth service acquires and manages depth estimation models. Models are Hailo Executable Format (HEF) files pre-compiled for the Hailo-10H NPU.

## Supported Models (Hailo-10H, v5.2.0)

### Recommended ⭐

**scdepthv3** - Self-Correcting Depth V3
- Source: https://github.com/JiawangBian/sc_depth_pl/
- Input Resolution: 256x320x3
- FPS: 719 (Batch Size=1)
- RMSE: 0.48
- Best accuracy/speed balance for monocular depth estimation
- HEF Download: https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/scdepthv3.hef

### Alternative Options

**fast_depth**
- Source: https://github.com/dwofk/fast-depth
- Input Resolution: 224x224x3
- FPS: 2288 (Batch Size=1)
- RMSE: 0.61
- Highest throughput; lower accuracy
- HEF Download: https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/fast_depth.hef

**depth_anything_v2_vits**
- Source: https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf
- Zero-shot depth estimation; excellent generalization
- HEF Download: https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/depth_anything_v2_vits.hef

**depth_anything_vits**
- Source: https://huggingface.co/LiheYoung/depth-anything-small-hf
- Zero-shot depth estimation; good generalization
- HEF Download: https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/depth_anything_vits.hef

## Installation

### Automatic Download (via `install.sh`)

✅ **IMPLEMENTED** - The installer automatically downloads models:

```bash
sudo ./install.sh
```

The installer:
1. ✅ Creates `/var/lib/hailo-depth/resources/models/` directory
2. ✅ Downloads model HEF from Hailo Model Zoo S3 bucket
3. ✅ Validates file size and integrity
4. ✅ Sets appropriate permissions for `hailo-depth` service user
5. ✅ Handles download errors gracefully

**Default Behavior:**
- Uses `scdepthv3` by default (recommended model)
- Skips download if model already exists
- Fails installation if download cannot be completed

### Manual Download

If you prefer to download and place models manually:

```bash
# Create model directory
sudo mkdir -p /var/lib/hailo-depth/resources/models

# Download scdepthv3 (recommended)
curl -fsSL -o /tmp/scdepthv3.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/scdepthv3.hef
sudo mv /tmp/scdepthv3.hef /var/lib/hailo-depth/resources/models/

# Or download fast_depth for higher throughput
curl -fsSL -o /tmp/fast_depth.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/fast_depth.hef
sudo mv /tmp/fast_depth.hef /var/lib/hailo-depth/resources/models/

# Set permissions
sudo chown hailo-depth:hailo-depth /var/lib/hailo-depth/resources/models/*.hef
sudo chmod 644 /var/lib/hailo-depth/resources/models/*.hef
```

## Configuration

To use a different model, edit `/etc/hailo/hailo-depth.yaml`:

```yaml
model:
  name: "scdepthv3"  # or "fast_depth", "depth_anything_v2_vits", etc.
  type: "monocular"
  keep_alive: -1  # Keep model loaded indefinitely
```

Then reload the service:

```bash
sudo systemctl restart hailo-depth.service
journalctl -u hailo-depth.service -f  # Monitor startup
```

## Model Download URLs Reference

All URLs are for **Hailo-10H** with **Dataflow Compiler v5.2.0**:

| Model | Size | URL |
|-------|------|-----|
| scdepthv3 | ~150-200 MB | https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/scdepthv3.hef |
| fast_depth | ~100-150 MB | https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/fast_depth.hef |
| depth_anything_v2_vits | ~100-150 MB | https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/depth_anything_v2_vits.hef |
| depth_anything_vits | ~100-150 MB | https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/depth_anything_vits.hef |

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "Failed to download model" | Network timeout or URL unreachable | Check internet connection; try manual download |
| "Downloaded file seems too small" | Corrupted or incomplete download | Delete file and retry: `sudo rm /var/lib/hailo-depth/resources/models/*.hef` |
| "curl: command not found" | curl not installed | `sudo apt install curl` |
| "Permission denied" when running service | Wrong file/directory ownership | `sudo chown -R hailo-depth:hailo-depth /var/lib/hailo-depth/` |
| Service won't start | Model file missing | Verify with `ls -la /var/lib/hailo-depth/resources/models/` and run `sudo ./install.sh` |

## Model Zoo Repository

For latest models and documentation:
- **GitHub Repository**: https://github.com/hailo-ai/hailo_model_zoo
- **Documentation**: Available in the repository at `docs/public_models/HAILO10H/HAILO10H_depth_estimation.rst`
- **Local Clone**: `/path/to/repo/hailo_model_zoo/` (available as Git submodule)

## Runtime Model Loading

Once the HEF file is in place:

1. Service starts and loads config from `/etc/hailo/hailo-depth.yaml`
2. Looks for model HEF at `/var/lib/hailo-depth/resources/models/{model_name}.hef`
3. Compiles HEF to Hailo-10H device memory on first inference (see HAILORT_INTEGRATION.md)
4. Keeps model loaded in device memory per `keep_alive` setting
5. Persists across HTTP requests until unloaded

## Next Steps

- See **HAILORT_INTEGRATION.md** for actual inference implementation
- See **ARCHITECTURE.md** for service design details
- See **API_SPEC.md** for inference endpoint documentation
