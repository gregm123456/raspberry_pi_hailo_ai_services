# System Setup: Hailo-10H on Raspberry Pi 5

**Initial system configuration for Hailo-10H NPU on Raspberry Pi 5 with AI HAT+ 2.**

This is **step zero**—run this *before* installing any AI services. After you bolt your AI HAT+ 2 into the Pi and power on for the first time, these setup steps prepare the OS and kernel driver so the NPU can be used.

## Prerequisites

- **Hardware:** Raspberry Pi 5 with AI HAT+ 2 (Hailo-10H NPU physically installed)
- **OS:** 64-bit Raspberry Pi OS Trixie (first boot, not yet configured)
- **Connectivity:** SSH or physical terminal access

## Quick Start

```bash
cd system_setup
bash install.sh
```

The script will:
1. ✓ Validate prerequisites
2. ✓ Update Raspberry Pi OS and firmware
3. ✓ Install Hailo kernel driver (`hailo-h10-all`)
4. ✓ Reboot and verify

**Estimated time:** 10–15 minutes (mostly waiting for reboots)

## After Installation

Once the reboot completes, verify everything is working:

```bash
bash verify.sh
```

Expected output:
```
✓ Hailo device detected at /dev/hailo0
✓ Kernel module loaded (hailo-10h v4.17.0)
✓ Firmware loaded successfully
```

If any checks fail, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Detailed Steps

For a step-by-step walkthrough with explanations and troubleshooting, see [SETUP.md](SETUP.md).

## What This Does (And Doesn't)

**Installs:**
- Latest Raspberry Pi OS updates and firmware
- Hailo kernel device driver (`hailo-h10-all` package)
- Hailo RT middleware and firmware for Hailo-10H

**Does NOT:**
- Set up user accounts or permissions (services do this themselves)
- Install AI models or runtime environments
- Configure systemd services (each service handles its own setup)

## Next Steps

Once `verify.sh` passes, you're ready to install AI services. Start with:
- **[hailo-ollama](../system_services/hailo-ollama/)** — LLM inference with Ollama API
- Other services will be available in `system_services/`

Each service's README will reference this setup as a prerequisite.

## Logs

Installation logs are saved to `system_setup_install_*.log` for troubleshooting.

---

**Reference:** [System Setup Documentation](../reference_documentation/system_setup.md) | [Raspberry Pi AI Docs](https://www.raspberrypi.com/documentation/computers/ai.html)
