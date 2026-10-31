# Raspberry Pi OS and Hailo Update Plan

**Goal:** Update the Pi's regular OS packages, make sure the current Hailo
services still work, and then consider a Hailo stack update separately.
New models and Gradio features are out of scope; we'll plan those after this.

**Target:** Raspberry Pi 5 + AI HAT+ 2 (Hailo-10H), accessed over Tailscale
as `gregm@pi5ai2sd`.

This is a hobby project, so keep it practical: check what is installed, make
one category of change at a time, and jot down what happened. No maintenance
window or disk-image backup is required. If something goes wrong, stop,
capture the error, and figure out the next step before piling on more changes.

## Progress

| Step | Status | Notes |
|---|---|---|
| 1. Note the current state | Done | OS/Hailo baseline and service health captured; Greg reports that inference for the installed models was tested through the portal and worked. |
| 2. Update Raspberry Pi OS packages | Done | Full Trixie upgrade completed and Pi rebooted successfully into kernel 6.18.50. Apt removed `pcmanfm` as predicted; `pcmanfm-pi` remains installed. |
| 3. Check that existing Hailo services still work | Done | Post-reboot HAILO10H detection, portal, healthy service endpoints, and inference verified. Greg confirmed Vision's autostart state and Florence's omission from the UI are intentional; Florence is not an in-scope service. |
| 4. Update Hailo software, if appropriate | Done | Driver, firmware, runtime, Tappas, and Python bindings are all 5.5.0. CLIP, Pose, Depth, Piper, and concurrency pass. Vision initially appeared image-independent, but after a reboot it correctly describes distinct images. Ollama untested. |

Use `Not started`, `In progress`, `Done`, or `Blocked`. Add a short result
below each step and update this table as you go.

## A few useful rules

- Keep OS-package updates and Hailo-stack updates as separate steps so a
  problem is easier to diagnose.
- A `hailort` Git submodule update does not update the software installed on
  the Pi.
- Keep Hailo's driver, firmware, runtime, and Python bindings compatible.
  `hailortcli fw-control identify` is useful, but it does not report every
  layer's version.
- Do not install new HEFs or models as part of these updates.
- `hailo-ollama` is a special case in this repo: test it separately from
  services using the device manager, not at the same time.
- The repo's current Hailo install instructions disagree about package names
  and versions. Check what the Pi actually uses rather than assuming either
  set of instructions is right.
- On this Pi, the loaded Hailo 5.3.0 driver creates `/dev/h1x-0`; it does not
  create `/dev/hailo0`. Check the observed node and HailoRT device detection;
  do not create a compatibility symlink as part of this update.
- `hailo-all` is the Hailo-8 metapackage and conflicts with the Raspberry Pi
  repository's Hailo-10 `hailo-h10-all` metapackage. Do not switch package
  families without first verifying the complete driver/runtime/Python package
  set needed by this existing 5.3.0 installation.
- Candidate HailoRT 5.5.0 Hailo-10H binaries were found on Hailo's public
  `dev-public.hailo.ai/2026_10/Hailo10/` host. The GitHub v5.5.0 release has
  no binary assets; do not treat its source tag as an installable package.
  The Developer Zone sign-in is separate from these public package URLs.
  Package availability alone does not establish kernel or service-venv
  compatibility; verify those before installing.

## Step 1 — Note the current state

Connect to the Pi:

```bash
ssh gregm@pi5ai2sd
```

Check OS, kernel, free space, and installed Hailo packages:

```bash
date --iso-8601=seconds
cat /etc/os-release
uname -a
df -h /
dpkg-query -W -f='${binary:Package}\t${Version}\n' 'hailo*' 2>&1
apt-cache policy hailo-all hailo-h10-all hailort hailort-pcie-driver hailo-tappas-core
hailortcli --version
hailortcli fw-control identify
ls -l /dev/hailo0
lsmod | grep -i hailo
```

Some package names or commands may not exist on this Pi; just note that.
Record the installed package names and sources, runtime and firmware versions,
device architecture, and whether `/dev/hailo0` exists.

See which services are running and whether any have failed:

```bash
systemctl list-units --type=service --all 'hailo*'
systemctl --failed
```

Before changing anything, try the representative inferences you normally
use, and note what works. Include the portal at `http://127.0.0.1:7860`.
If practical, test CLIP, Vision, Whisper, OCR, Pose, Depth, and Piper. Only
test services that are installed and expected to work.

The repo has some useful scripts, but they do not cover every service:

```bash
cd ~/raspberry_pi_hailo_ai_services
bash test_services.sh
python3 test_services.py
bash device_manager/test_concurrent_services.sh
```

Run them if the checkout and dependencies are available; record errors rather
than treating them as a complete test suite. If you test Ollama, stop the
device-manager clients first and restore their prior state afterward.

### Step 1 results

- Date: 2026-10-31 10:59 PDT.
- OS / kernel: Debian GNU/Linux 13.5 (trixie), arm64; Linux 6.18.34+rpt-rpi-2712. Root filesystem has 19 GB free (58 GB total).
- Hailo packages and versions: `hailo-all` 5.1.1 (its package description identifies it as the Hailo-8 metapackage); `hailo-tappas-core`, `hailort`, and `hailort-pcie-driver` 5.3.0; `hailo-gen-ai-model-zoo` 5.2.0; `hailo-models` 1.0.0-2. `hailo-h10-all` is not installed. Apt offers 5.1.1 for `hailo-all` and `hailo-h10-all`, and 5.1.0 for Tappas; installed 5.3.0 packages have no matching repository candidate in the current apt metadata. No apt holds.
- Hailo runtime / firmware / device: HailoRT-CLI 5.3.0; `fw-control identify` succeeds and reports firmware 5.3.0 and HAILO10H. `hailo1x_pci` is loaded and `/dev/h1x-0` exists (character device, mode `crw-rw-rw-`). `/dev/hailo0` is not created by this installed driver.
- Services and known issues: CLIP, Depth, Device Manager, Florence, Piper, Pose, Vision, and Web Portal are active; OCR and Ollama are inactive; Face is not found; `hailort.service` is masked. `systemctl --failed` reports no failed units.
- Portal and inference checks: Portal responds HTTP 200. Health checks return healthy/model-loaded for CLIP (5000), Vision (11435), Pose (11440), Depth (11439), and Piper (5003). Whisper (11437), OCR (11436), and Ollama (11434) are inactive/unavailable. Greg reports that inference for the installed models was tested through the portal and worked; some models are not currently loaded. `test_services.sh` ran but emitted `bc` syntax errors for its timing calculations and suppresses request output, so its exit status is not evidence of inference success.
- Test script results: `device_manager/test_concurrent_services.sh` completed; sequential and concurrent health checks reported CLIP and Vision models loaded. This script checks health endpoints, not concurrent inference.
- Notes: No system changes have been made. Package metadata identifies the installed generic `hailo-all` as Hailo-8 support, while the detected device is Hailo-10H. The Pi's active Hailo runtime/driver/Tappas components are 5.3.0 and work with the HAILO10H according to the CLI; the exact origin of those installed `.deb` files is not recorded by apt. Use `/dev/h1x-0` for this host rather than treating the missing `/dev/hailo0` as device failure.

**Check before continuing:** Know which services worked before the updates
and what Hailo package family/version is actually installed.

## Step 2 — Update Raspberry Pi OS packages

Refresh package information and preview the package changes:

```bash
sudo apt update
sudo apt-get -s full-upgrade
```

Review the simulation. This is a package update within the current OS
release, not a move to a new Raspberry Pi OS release. Pay attention to
removals and any Hailo packages in the list.

If Hailo packages are included, don't accidentally update them in this step.
You can pause and decide whether to hold the specific installed Hailo
packages temporarily, then repeat the simulation. Write down any holds so
they can be removed when you get to Step 4. If the transaction is confusing,
stop and inspect it rather than guessing.

When the proposed OS update looks reasonable:

```bash
sudo apt full-upgrade
```

Read apt's final prompt before accepting. If it proposes unexpected removals
or Hailo package changes, cancel and reconsider the package selection. No
need to run `apt autoremove` as part of this plan.

If apt updates the kernel or asks for a reboot:

```bash
sudo systemctl reboot
```

Reconnect after it comes back:

```bash
ssh gregm@pi5ai2sd
uname -a
systemctl --failed
```

### Step 2 results

- Date: 2026-10-31.
- Package changes made: `sudo apt update` completed. `apt-get -s full-upgrade` proposed 424 upgrades, 35 new packages, and removal of `pcmanfm`; it also included kernel 6.18.50 packages. Greg authorized the full recommended transaction, including dependent removals. `sudo DEBIAN_FRONTEND=noninteractive apt full-upgrade -y` completed successfully; kernel image and headers 6.18.50 were installed. Apt history confirms `pcmanfm` was removed while `pcmanfm-pi` remains installed. `dpkg --audit` reports no unfinished packages.
- Were Hailo packages unchanged?: No Hailo package changes appeared in the simulated transaction.
- Any package holds applied:
- Rebooted?: Yes; Greg confirmed the Pi returned successfully and uptime was about six minutes at 12:41 PDT.
- New kernel: Linux 6.18.50+rpt-rpi-2712, active after reboot.
- Errors or surprises: `pcmanfm` is among the dependent removals and is authorized.
- Notes: No `apt autoremove` was run. Apt history contains no Hailo package install, upgrade, or removal. Root filesystem has 18 GB free after the upgrade.

**Check before continuing:** The Pi is reachable and the OS update completed.
If the Hailo packages changed too, note their new versions; treat that as a
Hailo update and include it in Step 4's checks.

## Step 3 — Check existing Hailo services

Check the device and driver after the OS update:

```bash
hailortcli --version
hailortcli fw-control identify
ls -l /dev/hailo0
lsmod | grep -i hailo
sudo journalctl -k -b --no-pager | grep -i hailo
systemctl --failed
```

Confirm that the device is detected as Hailo-10H and firmware loads. If the
kernel changed, check that the Hailo driver loaded too.

Check that the services which worked in Step 1 still work. Start with the
device manager, then use the same test requests and scripts as before. Health
URLs for common services include:

```bash
curl -fsS --max-time 10 http://127.0.0.1:5000/health
curl -fsS --max-time 10 http://127.0.0.1:11435/health
curl -fsS --max-time 10 http://127.0.0.1:11437/health
curl -fsS --max-time 10 http://127.0.0.1:11436/health
curl -fsS --max-time 10 http://127.0.0.1:11440/health
curl -fsS --max-time 10 http://127.0.0.1:11439/health
curl -fsS --max-time 10 http://127.0.0.1:5003/health
```

Only run checks for services that are installed; use their API docs if a
health path differs. Health checks are not a substitute for a real inference.
Look at device-manager logs if services fail:

```bash
sudo journalctl -u hailo-device-manager.service -n 100 --no-pager
```

For the portal, confirm `hailo-web-portal` is running and open
`http://127.0.0.1:7860` locally on the Pi. To view it from your computer, use
SSH forwarding:

```bash
ssh -L 7860:127.0.0.1:7860 gregm@pi5ai2sd
```

Then open `http://127.0.0.1:7860` on your computer.

If you test Ollama, stop the device-manager services first, test Ollama on its
own, then restore the previous service state. Compare results with Step 1.
If an existing service regressed, pause here and investigate before updating
more software.

### Step 3 results

- Date: 2026-10-31 12:42 PDT.
- Device / driver / firmware: Kernel 6.18.50 is active; `hailo1x_pci` loads and creates `/dev/h1x-0`. HailoRT CLI and HAILO10H firmware remain 5.3.0; `fw-control identify` succeeds. `/dev/hailo0` remains absent as expected for this installed driver.
- Service health and inference checks: After reboot, CLIP (5000), Pose (11440), Depth (11439), and Piper (5003) report healthy and models loaded. Vision (11435) is stopped and disabled; Greg clarified that the service was not configured to auto-start, so this is expected. Whisper and OCR were inactive before the OS update and remain unavailable; Ollama was inactive before and after the OS update. Greg confirmed that the post-reboot Gradio UI tests succeeded and the existing models he tested are running. Florence (11438) responds unhealthy because it cannot find `python3-h10-hailort`; Greg clarified that Florence was intentionally omitted from the UI, so it is not part of this update's service acceptance checks.
- Device-manager logs / concurrency:
- Ollama, if tested: Not tested; inactive before and after the OS upgrade.
- Portal: `hailo-web-portal.service` is active. The first probe requested `/health`, which returns HTTP 404; confirm the portal root page instead.
- Errors or performance changes: `systemctl --failed` reports no failed units. Florence's health endpoint reports missing Hailo-10 Python bindings; Florence is out of the tested/in-scope UI services per Greg.
- Notes: Hailo package versions did not change during the OS upgrade. Do not enable Vision or modify Florence as part of this plan. Greg's post-reboot Gradio inference verification clears the service gate for the separate Hailo stack update.

**Check before continuing:** The services that worked before still work after
the OS update, or any regression is understood.

## Step 4 — Update Hailo software, if appropriate

First decide whether a Hailo update is needed. A new Model Zoo tag does not
mean a matching Pi package is available, and updating the repo's `hailort`
submodule alone does not install a runtime.

On 2026-10-31, HEAD requests to Hailo's public Hailo-10 directory returned
HTTP 200 for these 5.5.0 candidates (not downloaded or installed):

- `https://dev-public.hailo.ai/2026_10/Hailo10/hailort-pcie-driver_5.5.0_all.deb`
- `https://dev-public.hailo.ai/2026_10/Hailo10/hailort_5.5.0_arm64.deb`
- `https://dev-public.hailo.ai/2026_10/Hailo10/hailo-tappas-core_5.5.0_arm64.deb`
- `https://dev-public.hailo.ai/2026_10/Hailo10/hailort-5.5.0-cp313-cp313-linux_aarch64.whl`

The GitHub release tag has no binary assets. Before using these direct vendor
downloads, verify their package metadata/checksums, kernel-driver compatibility
with the current kernel, and the Python binding requirements of every active
service environment. The apt repository's 5.1.1 Hailo-10 metapackage is a
different package family; do not mix it into the working 5.3.0 install without
reviewing the resulting transaction.

Verification performed after the OS update:

- All four artifacts downloaded over HTTPS from Hailo's public
  `dev-public.hailo.ai` host. Local SHA-256 values:
  - PCIe driver: `d1600c40160934ab8cc68525b9263e02060705ac3eefc95e1046c4e0399d4f0f`
  - Runtime: `853a4467a35c59986c009fe8156c48e42a5763e93ee6509abe90a7b6816392a5`
  - Tappas: `26d244482a429d495a33b5ff15a76c5ee5596c941a23d0a1a55da5f15edc913e`
  - CPython 3.13 arm64 wheel: `4d37647f6643ce9e352c06887540ce7fc99d627f5b2be317ebb912a4d727a859`
- Debian metadata confirms the PCIe package is `h10-hailort-pcie-driver`
  5.5.0 and replaces the Hailo-8 `hailort-pcie-driver`; the HailoRT and
  Tappas packages are both arm64 version 5.5.0. The Python wheel is
  `hailort` 5.5.0, requires Python >=3.10,<3.14 and NumPy, and matches the
  Pi's CPython 3.13 arm64 environment.
- The driver package uses DKMS with `build-essential` and reloads
  `hailo1x_pci` during installation. Kernel 6.18.50 headers and DKMS are
  installed; the current 5.3.0 module is registered for the running kernel.
- An apt simulation proposes exactly the expected replacement: remove
  `hailo-all` 5.1.1 (Hailo-8 metapackage) and `hailort-pcie-driver` 5.3.0;
  install `h10-hailort-pcie-driver` 5.5.0; upgrade `hailort` and
  `hailo-tappas-core` to 5.5.0. No unrelated packages are proposed for
  installation, upgrade, or removal (apt also listed unrelated old packages
  as eligible for a separately-invoked autoremove; do not run autoremove).
- The device manager is the only in-scope service directly importing
  `hailo_platform`; update its dedicated venv wheel. Do not update Model Zoo
  pins, HEFs, or Florence as part of this plan.

Before installing anything, identify a matching Hailo-10H set of:

- Kernel driver, supported with the Pi's current kernel.
- Firmware.
- Host HailoRT runtime and CLI.
- Tappas/core libraries, if the installed services need them.
- `hailo_platform` Python bindings for the device manager and any service
  environments that use them.

Check which package source and versions are available for this Pi, and
confirm the installation instructions and required reboot. The repository
currently has conflicting Hailo setup instructions, so verify the package
family against the Pi's actual installation. If the compatible packages
aren't available or the versions don't line up, leave the current stack as-is
and record why.

If proceeding:

1. Note the current versions and which services are running.
2. Stop the affected services.
3. Install only the matching Hailo packages/bindings, following the vendor's
   instructions for that exact version. Review the apt transaction so it
   doesn't unexpectedly pull in unrelated changes.
4. Reboot if required.
5. Check the runtime, driver, firmware, device, and Python bindings
   individually. `hailortcli fw-control identify` alone isn't enough.
6. Start the device manager, then the services that were running before.
   Test them one at a time, then try the existing concurrency check.
7. Test Ollama separately if it is part of the current setup, and confirm the
   portal still loads.
8. Remove any temporary apt holds from Step 2 when appropriate:

   ```bash
   sudo apt-mark unhold PACKAGE_NAME
   ```

   Replace `PACKAGE_NAME` with each exact package name you recorded; don't
   run this placeholder command literally.

Don't update Model Zoo source pins or install new HEFs/models in this step.

### Step 4 results

- Date: 2026-10-31.
- Decision to update or stay put, and why: Proceed with Hailo 5.5.0; Hailo publishes a matching Hailo-10 driver, runtime, Tappas, and CPython 3.13 wheel. Apt simulation shows only the expected Hailo-8-to-Hailo-10 package-family replacement.
- Hailo packages / source / versions before and after: Before: HailoRT, PCIe driver, and Tappas 5.3.0; generic `hailo-all` 5.1.1. Installed from Hailo public `dev-public.hailo.ai/2026_10/Hailo10/`: `hailort` 5.5.0, `hailo-tappas-core` 5.5.0, and Hailo-10-specific `h10-hailort-pcie-driver` 5.5.0. As expected, apt removed the Hailo-8 `hailo-all` 5.1.1 metapackage and generic `hailort-pcie-driver` 5.3.0. No autoremove was run.
- Runtime / driver / firmware / Python binding results: Immediately after the package install the endpoint still ran 5.3.0 firmware: `hailortcli fw-control identify` failed with `HAILO_SOC_CONNECT`, and the kernel logged `Mismatch Driver version pcie driver 5:5:0 pci_ep driver 5:3:0` / `driver_compatible is false`. A plain reboot (no power cycle) fixed it: DKMS module 5.5.0, HailoRT-CLI 5.5.0, and firmware 5.5.0 (HAILO10H) all report correctly and `/dev/h1x-0` exists. The 5.5.0 wheel (re-downloaded after the reboot cleared /tmp; SHA-256 matched `4d37647f...`; kept in `~/hailo-5.5.0-staging/`) was installed with `pip --no-deps --force-reinstall` into the eight venvs that had `hailort` (clip, depth, device-manager, florence, ocr, pose, vision, whisper); all import 5.5.0 from their own site-packages. The piper and web-portal venvs have no `hailort`. A stale `hailort` 5.3.0 copy remains in `~/.local/lib/python3.13/site-packages`; venv copies take precedence and it was left untouched.
- Services and inference checks: Started the device manager, then CLIP, Depth, Pose, Piper, Portal, and Vision (Vision is disabled for autostart, so it was started manually for testing). All healthy and model-loaded; portal root HTTP 200; `systemctl --failed` empty. Inference: CLIP classified `dog.png` as "a cat" at 0.98 (the file is a cat photo, so correct), 144 ms. Pose HTTP 200 with 0 poses (no person in image), 210 ms. Depth HTTP 200, 50 ms. Piper returned a valid 22050 Hz mono WAV in 1.2 s. Vision: see Errors.
- Concurrency check: Concurrent CLIP, Pose, and Depth requests all returned HTTP 200; `device_manager/test_concurrent_services.sh` completed.
- Ollama, if tested: Not tested; inactive before and after the OS update.
- Portal: Root page HTTP 200 after the update; Greg should click through the UI for a final check.
- Errors or remaining questions: **Vision output looks image-independent.** Vision loads the VLM in about 30 s and returns HTTP 200, but the text barely depends on the image: a cat photo (`dog.png`) and `card.png` both gave "bustling marketplace" for "Describe this image", and the same degenerate text for "What animal or object is in this image?"; an earlier request called the cat "a person walking through a forest". This could be a 5.5.0 regression in the VLM image path or pre-existing behavior; no pre-update Vision output was captured to compare (Greg's UI test of Vision was before the Hailo update). Test note: `temperature: 0` is rejected by HailoRT ("Temperature should be higher than '0'", HTTP 500); that was my test's mistake, not a regression. **Update:** Greg confirmed in the portal UI that Vision output depends only on the prompt, never the image. Code review: `hailo_vision_server.py` builds the correct structured prompt (`{"type":"image"}` + text) and passes a 336x336 RGB frame; the device manager's `VlmChatHandler` calls `VLM.generate_all(prompt, frames=...)`, whose 5.5.0 signature is unchanged; no errors in the journal. The Qwen2-VL HEF was provisioned under the older GenAI zoo pin (submodule is at v5.2.0), so the likely cause is a HEF/runtime mismatch (5.5.0 runtime with an older-generation VLM HEF) rather than service code. Not yet confirmed whether it was already broken on 5.3.0. **Follow-up:** the installed `Qwen2-VL-2B-Instruct.hef` was 2,344,333,123 bytes, i.e. the v5.1.1 build (Nov 2025). `dev-public.hailo.ai/v5.5.0/blob/Qwen2-VL-2B-Instruct.hef` (3,126,526,675 bytes, SHA-256 `ca662f61...affa9`, kept in `~/hailo-5.5.0-staging/`) is the 5.5.0 build; it was swapped in (old file kept as `Qwen2-VL-2B-Instruct.hef.v5.1.1.bak` in the model dir). It loads fine, but Vision initially still returned identical text after replacing the HEF (before reboot). After Greg rebooted, a repeat test with the same prompt and three images produced distinct, image-appropriate results: `dog.png` -> cat on a lap; `card.png` -> credit card; `text.png` -> poem. This confirms Vision works with the new 5.5.0 HEF after reboot; the cause of the pre-reboot behavior is unknown. Whisper, OCR, and Florence were not part of this check (Florence still reports missing `python3-h10-hailort`, as before; out of scope per Greg).
- Notes: Sequence that worked: stop services, `apt install` the three local `.deb` files (driver/runtime/Tappas), reboot, install the wheel into venvs, restart services. No `apt autoremove` was run. Rollback, if needed: re-download the 5.3.0 files from `dev-public.hailo.ai/2026_04/Hailo10/` (no longer available from apt).

**Done when:** The existing Hailo services still work with the resulting
stack, or the reason for staying on the old stack is documented. Then we can
plan the new models and Gradio features separately.

- Final Vision check after reboot (2026-10-31): verified image-dependent responses for `dog.png`, `card.png`, and `text.png`; Step 4 is complete.
