# Detailed System Setup Guide: Hailo-10H on Raspberry Pi 5

This guide walks through each step of configuring your Raspberry Pi 5 to use the Hailo-10H NPU on the AI HAT+ 2. Read this if you want to understand what's happening under the hood, or if the automated `install.sh` encounters issues.

---

## Prerequisites Checklist

Before starting, verify:

- [ ] **Hardware physically installed:** AI HAT+ 2 is firmly seated in the PCIe M.2 slot on Raspberry Pi 5
- [ ] **Power:** Pi is powered on and booted (you can SSH in or access the terminal)
- [ ] **OS installed:** 64-bit Raspberry Pi OS Trixie is running
- [ ] **Connectivity:** You have SSH or terminal access
- [ ] **Internet:** The Pi has internet connectivity (for package downloads)

**Verify OS version:**
```bash
cat /etc/os-release | grep PRETTY_NAME
```

Expected: `PRETTY_NAME="Raspberry Pi OS (Trixie)"`

---

## Step 1: Update Raspberry Pi OS and Firmware

This ensures kernel and bootloader compatibility with the Hailo driver.

### Run Updates

```bash
sudo apt update
sudo apt full-upgrade -y
sudo rpi-eeprom-update -a
```

### What This Does

- **`apt update`** — Refreshes package lists from repositories
- **`apt full-upgrade`** — Installs latest OS patches and kernel (may take 5+ minutes)
- **`rpi-eeprom-update -a`** — Updates Raspberry Pi bootloader firmware

### Expected Output

```
Processing triggers for man-db (2.11.4-2) ...
Processing triggers for mailcap (2.1.53+nmu1) ...
Done.
```

### Troubleshooting

- **"Unable to locate package"** → Your package lists may be corrupted. Run `sudo apt clean` and retry.
- **Very slow download** → Normal on first upgrade. Can take 10+ minutes depending on internet.

---

## Step 2: Reboot (First)

```bash
sudo reboot
```

Wait for the Pi to restart. The kernel will be updated to the latest version. This is **required** before installing the Hailo driver.

**Verify reboot completed:** SSH back in or reconnect your terminal.

---

## Step 3: Install Hailo Dependencies

### Install DKMS

The Dynamic Kernel Module Support (DKMS) package allows the Hailo driver to compile against your current kernel:

```bash
sudo apt install dkms
```

### Install Hailo-10H Driver and Firmware

**Critical:** Use `hailo-h10-all` for AI HAT+ 2. Do NOT use `hailo-all` (that's for the older AI Kit).

```bash
sudo apt install hailo-h10-all
```

### Expected Output

```
Reading package lists... Done
Building dependency tree... Done
The following NEW packages will be installed:
  hailo-fw hailo-drivers hailo-libhailort hailo-pydev hailo-tappas
...
Processing triggers for man-db ...
Done.
```

### What Was Installed

- **hailo-drivers** — Kernel module (`hailo-h10h.ko`)
- **hailo-libhailort** — Runtime library for communicating with NPU
- **hailo-fw** — Firmware binary for the Hailo-10H
- **hailo-tappas** — Post-processing libraries for vision tasks

---

## Step 4: Reboot (Second)

```bash
sudo reboot
```

The Hailo kernel module will be compiled and loaded during boot. This is **required** for the NPU to be detected.

---

## Step 5: Verify Installation

After reboot, check that the driver and firmware loaded correctly.

### Check Device Presence

```bash
ls -la /dev/hailo0
```

**Expected output:**
```
crw-rw-r-- 1 root root 234, 0 Jan 30 10:22 /dev/hailo0
```

If `/dev/hailo0` is missing, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Query Hailo Device

```bash
hailortcli fw-control identify
```

**Expected output:**
```
Executing on device: 0000:01:00.0
Identifying board
Control Protocol Version: 2
Firmware Version: 4.17.0 (release,app,extended context switch buffer)
Logger Version: 0
Board Name: Hailo-8
Device Architecture: HAILO8L
Serial Number: <N/A>
Part Number: <N/A>
Product Name: <N/A>
```

**Note:** For AI HAT+ 2, `Serial Number`, `Part Number`, and `Product Name` often show `<N/A>`—this is normal and doesn't indicate a problem.

### Check Kernel Logs

```bash
dmesg | grep -i hailo
```

**Expected output should include:**
```
[    3.049657] hailo: Init module. driver version 4.17.0
[    3.051983] hailo 0000:01:00.0: Probing on: 1e60:2864...
[    3.052006] hailo 0000:01:00.0: enabling device (0000 -> 0002)
...
[    3.221043] hailo 0000:01:00.0: Firmware was loaded successfully
[    3.231845] hailo 0000:01:00.0: Probing: Added board 1e60-2864, /dev/hailo0
```

### Check All Three

Run the verification script to check all at once:

```bash
cd system_setup
bash verify.sh
```

---

## Summary: System Ready ✓

Once all verification checks pass, your system is configured and ready. The Raspberry Pi 5 can now:

- Load and communicate with the Hailo-10H NPU
- Run AI models accelerated by the NPU
- Support multiple concurrent services using the same device

### Next Steps

Install your first service:
- Start with [hailo-ollama](../system_services/hailo-ollama/) for LLM inference
- Or other services as they become available

---

## Reference

- [Official Hailo-10H Setup Docs](../reference_documentation/system_setup.md)
- [Raspberry Pi AI Documentation](https://www.raspberrypi.com/documentation/computers/ai.html)
- [Hailo Installation Guide](https://github.com/hailo-ai/hailo-rpi5-examples)

For common problems and solutions, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
