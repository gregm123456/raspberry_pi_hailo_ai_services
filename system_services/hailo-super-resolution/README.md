# Hailo Super-Resolution

SPANF x4 super-resolution for the Hailo-10H. The service accepts JPEG, PNG,
and other Pillow-readable images, preserves their aspect ratio, and returns a
4x image. It uses overlapping 512x512 input tiles, so images do not need to be
512x512 squares. Requests are limited to 4,000,000 input pixels to bound memory
use; common 512x512 and 1024x1024 images are supported.

The HEF is the v5.5.0 Hailo-10H build published by the Hailo Model Zoo. The
underlying SPANF model is released under the MIT license by
[NTIRE2025_ESR](https://github.com/Amazingren/NTIRE2025_ESR).

## Install

Install the Hailo-10H driver/runtime and `hailo-device-manager` first, then run:

```bash
sudo ./install.sh
```

The installer creates an isolated venv, downloads the HEF to
`/var/lib/hailo-super-resolution/models/spanf_x4.hef`, and enables the service.
It binds to `127.0.0.1:11442` by default; the web portal uses this local API.

## Use

Upload an image in the portal's **Super Resolution** tab, then select **Upscale
4x**. The output dimensions are exactly four times the input dimensions.

See [API_SPEC.md](./API_SPEC.md) for the REST contract and
[TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for health and capacity checks.
