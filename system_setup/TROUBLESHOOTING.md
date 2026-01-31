# Troubleshooting: Hailo-10H System Setup

Common issues during installation and verification, with solutions.

---

## Device Not Detected (`/dev/hailo0` Missing)

### Symptoms
- `verify.sh` shows: ✗ Device node /dev/hailo0 not found
- `ls -la /dev/hailo0` returns: No such file or directory

### Causes & Solutions

**1. Kernel Module Not Loaded**

Check if the module is loaded:
```bash
lsmod | grep hailo
```

If empty, the driver didn't load during boot. This usually means:

- **Physical connection issue** — Verify AI HAT+ 2 is firmly seated in the M.2 PCIe slot
- **Missing reboot** — Did you reboot after installing `hailo-h10-all`? The driver compiles on first boot.
- **Kernel mismatch** — Run: `uname -r` and check recent kernel updates. If unexpected, try: `sudo apt install --reinstall -y hailo-h10-all`

**Solution:**
```bash
# Reboot and check
sudo reboot
# After boot:
lsmod | grep hailo
```

**2. PCIe Device Not Detected**

Check if the NPU is visible on the PCIe bus:
```bash
lspci | grep -i hailo
```

Expected output:
```
01:00.0 Multimedia controller: Hailo Ltd. Hailo-10 AI Accelerator
```

If not visible:
- **Check BIOS/firmware** — Run: `sudo vcgencmd bootloader_version`
- **Power cycle** — Shut down completely, wait 30 seconds, power on
- **Reseat the card** — Power off, reseat AI HAT+ 2 in M.2 slot, power on

**3. Package Installation Failed**

Check if `hailo-h10-all` installed correctly:
```bash
dpkg -l | grep hailo
```

Expected packages:
- `hailo-drivers`
- `hailo-libhailort`
- `hailo-fw`
- `hailo-tappas`

If any are missing, try reinstalling:
```bash
sudo apt install --reinstall -y hailo-h10-all
```

---

## Permission Denied on `/dev/hailo0`

### Symptoms
- Device exists but: ✗ Device readable and writable
- Running commands fails with: `Permission denied`
- Current user is not `root`

### Cause

By default, `/dev/hailo0` is only readable/writable by `root`. Services typically run as their own user (e.g., `hailo-ollama` runs as user `hailo`).

### Solution

**Option 1: Add user to dialout/plugdev groups**

(Services typically handle this in their own install scripts)

```bash
sudo usermod -aG dialout,plugdev $USER
# Logout and log back in for group membership to take effect
```

**Option 2: Adjust device permissions (less secure)**

```bash
sudo chmod 666 /dev/hailo0  # Temporary (lost on reboot)
```

For permanent permissions, services should set up udev rules or handle this in their installation.

---

## Firmware Version Mismatch or Not Responding

### Symptoms
- `hailortcli fw-control identify` hangs or fails
- ✗ Firmware detected and responsive
- ✗ hailortcli available but device not responding

### Causes & Solutions

**1. Device Not Ready**

The firmware may not have loaded yet or USB bus needs to settle:

```bash
# Try again:
hailortcli fw-control identify

# If still failing:
sudo dmesg | tail -20  # Check for I/O errors
```

**2. Kernel Module Not Loaded**

See "Device Not Detected" above.

**3. Old libhailort Cached**

Old runtime libraries may be conflicting. Clear cache and reinstall:

```bash
sudo apt install --reinstall -y hailo-libhailort
```

---

## Conflicting Hailo Packages

### Symptoms
- Installation fails with: `E: Unable to correct problems, you have held broken packages`
- Message about `hailo-all` vs `hailo-h10-all`

### Cause

The repository might have older `hailo-all` package installed (for AI Kit, not AI HAT+ 2). These conflict.

### Solution

Remove the conflicting package:

```bash
sudo apt remove -y hailo-all hailo-drivers
sudo apt autoremove

# Then reinstall the correct one:
sudo apt install -y hailo-h10-all
```

---

## OS Update Hung or Failed

### Symptoms
- `install.sh` stuck on: "Updating Raspberry Pi OS and firmware..."
- Apt locks held by other processes
- Out of disk space

### Solutions

**1. Release Apt Lock**

```bash
sudo lsof /var/lib/apt/lists/lock  # See what's holding it
sudo killall apt apt-get           # Force-release (use with caution)
sudo rm -f /var/lib/apt/lists/lock
```

**2. Check Disk Space**

```bash
df -h /
```

If root partition is >90% full, free space before retrying:

```bash
sudo apt clean              # Remove package cache
sudo journalctl --vacuum-time=7d  # Clean old logs
```

**3. Manually Complete Update**

```bash
sudo apt update
sudo apt full-upgrade -y
```

Then re-run `install.sh`.

---

## Kernel Logs Show Errors

### Symptoms
- `dmesg | grep hailo` shows error messages
- Common errors:
  - `hailo 0000:01:00.0: Probing: Could not communicate with control...`
  - `hailo 0000:01:00.0: Failed to load firmware`

### Diagnosis

Display full details:
```bash
dmesg | grep -i hailo | tail -20
```

**Common issues:**

- **"Could not communicate"** → Device not responding, try power cycle + reseat
- **"Failed to load firmware"** → Corrupt package, reinstall: `sudo apt install --reinstall -y hailo-fw`
- **"Memory allocation failed"** → Low RAM, try rebooting into minimal mode first

---

## Cannot Reinstall After Failed Installation

### Symptoms
- Trying to reinstall but packages corrupt
- `dpkg` errors: "trying to overwrite..."

### Solution

**Break and fix package state:**

```bash
sudo apt --fix-broken install
sudo dpkg --configure -a
sudo apt install -y hailo-h10-all
```

If that doesn't work, do a clean slate:

```bash
sudo apt remove -y hailo-drivers hailo-libhailort hailo-fw hailo-tappas
sudo apt autoremove
sudo apt install -y hailo-h10-all
```

---

## Verify Script Shows Partial Failures

### Check Individual Items

Run individual verification commands manually:

```bash
# Device node
ls -la /dev/hailo0

# Kernel module
lsmod | grep hailo

# Firmware
hailortcli fw-control identify

# Device on PCIe
lspci | grep -i hailo

# Kernel logs
dmesg | grep -i hailo | tail -5
```

See the appropriate section above based on which command fails.

---

## Still Stuck?

### Collect Diagnostics

Gather information for debugging:

```bash
cat /etc/os-release | grep PRETTY_NAME
uname -r
dpkg -l | grep hailo
lsmod | grep hailo
lspci | grep -i hailo
dmesg | grep -i hailo
hailortcli fw-control identify
```

### Check Logs

- **Installation log:** `system_setup_install_*.log` in this directory
- **Kernel logs:** `sudo journalctl -k | grep hailo`
- **System messages:** `sudo journalctl -e | head -50`

### Resources

- [Hailo Documentation](https://github.com/hailo-ai/hailo-rpi5-examples)
- [Raspberry Pi AI Docs](https://www.raspberrypi.com/documentation/computers/ai.html)
- [System Setup Reference](../reference_documentation/system_setup.md)

---

## Report an Issue

If you've followed all troubleshooting steps and still have problems:

1. Collect diagnostics (above)
2. Check the installation and kernel logs
3. Verify your hardware setup (AI HAT+ 2 physically installed)
4. Try with a fresh SD card and minimal Raspberry Pi OS install if possible
