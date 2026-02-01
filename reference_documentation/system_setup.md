# AI HAT+ 2 System Setup for Raspberry Pi 5

This document contains the specific software and system setup instructions for the Raspberry Pi AI HAT+ 2 with Hailo-10H NPU, to be completed after initial installation and before downloading or running any models.

**Prerequisites:**
- Raspberry Pi 5
- 64-bit Raspberry Pi OS (Trixie)
- AI HAT+ 2 with on-board Hailo-10H NPU (physically installed)

---

## 1. Update Raspberry Pi OS

Ensure that the Raspberry Pi 5 is running Raspberry Pi OS Trixie with the latest software installed, and that it has the latest Raspberry Pi firmware:

```bash
$ sudo apt update
$ sudo apt full-upgrade -y
$ sudo rpi-eeprom-update -a
$ sudo reboot
```

For more information, see Update software and Update the bootloader configuration in the official Raspberry Pi documentation.

---

## 2. Install Required Dependencies

After updating your Raspberry Pi with the latest Raspberry Pi software and firmware, the following dependencies are required to use the Hailo-10H NPU:

- The Hailo kernel device driver and firmware
- Hailo RT middleware software
- Hailo Tappas core post-processing libraries

### AI HAT+ 2 Installation

**Note:** The AI HAT+ 2 requires the `hailo-h10-all` package (different from AI Kit/AI HAT+ which use `hailo-all`). These packages cannot co-exist.

To install the required dependencies for the AI HAT+ 2, open the Raspberry Pi Terminal and run the following commands:

```bash
$ sudo apt install dkms
$ sudo apt install hailo-h10-all
```

---

## 3. Reboot and Verify

After installing the required dependencies, you must reboot your Raspberry Pi 5.

```bash
$ sudo reboot
```

When your Raspberry Pi 5 has finished booting back up again, run the following command to check that everything is running correctly:

```bash
$ hailortcli fw-control identify
```

### Expected Output

If you see output similar to the following, you've successfully installed the NPU and its software dependencies:

```
Executing on device: 0001:01:00.0
Identifying board
Control Protocol Version: 2
Firmware Version: 5.1.1 (release,app)
Logger Version: 0
Device Architecture: HAILO10H
```

**Note for AI HAT+ 2:** The AI HAT+ 2 might show `<N/A>` for `Serial Number`, `Part Number`, and `Product Name`, or simply omit them in the `identify` output. This is expected and doesn't affect functionality.

### Verify Kernel Logs

Additionally, you can run `dmesg | grep -i hailo` to check the kernel logs, which is expected to output something like the following:

```
[    3.049657] hailo: Init module. driver version 4.17.0
[    3.051983] hailo 0000:01:00.0: Probing on: 1e60:2864...
[    3.051989] hailo 0000:01:00.0: Probing: Allocate memory for device extension, 11600
[    3.052006] hailo 0000:01:00.0: enabling device (0000 -> 0002)
[    3.052011] hailo 0000:01:00.0: Probing: Device enabled
[    3.052028] hailo 0000:01:00.0: Probing: mapped bar 0 - 000000000d8baaf1 16384
[    3.052034] hailo 0000:01:00.0: Probing: mapped bar 2 - 000000009eeaa33c 4096
[    3.052039] hailo 0000:01:00.0: Probing: mapped bar 4 - 00000000b9b3d17d 16384
[    3.052044] hailo 0000:01:00.0: Probing: Force setting max_desc_page_size to 4096 (recommended value is 16384)
[    3.052052] hailo 0000:01:00.0: Probing: Enabled 64 bit dma
[    3.052055] hailo 0000:01:00.0: Probing: Using userspace allocated vdma buffers
[    3.052059] hailo 0000:01:00.0: Disabling ASPM L0s
[    3.052070] hailo 0000:01:00.0: Successfully disabled ASPM L0s
[    3.221043] hailo 0000:01:00.0: Firmware was loaded successfully
[    3.231845] hailo 0000:01:00.0: Probing: Added board 1e60-2864, /dev/hailo0
```

---

## Summary

Once you have completed all three steps and verified that the Hailo NPU is properly detected, your Raspberry Pi 5 is ready to run AI models. The system is now configured at the OS and driver level, and you can proceed to:

- Install camera dependencies and run vision AI models
- Install and run Large Language Models (LLMs) with the Hailo Ollama server

For detailed instructions on running models, refer to the official Raspberry Pi AI documentation at https://www.raspberrypi.com/documentation/computers/ai.html

---

### Key Points for AI HAT+ 2

- **PCIe Gen 3.0**: Unlike the AI Kit, the AI HAT+ 2 automatically applies PCIe Gen 3.0 settings, so no manual configuration is needed
- **Package Name**: Always use `hailo-h10-all` for AI HAT+ 2 (not `hailo-all`)
- **Verification**: The `hailortcli fw-control identify` command confirms successful driver installation and NPU detection
