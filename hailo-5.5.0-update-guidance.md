# Hailo v5.5.0 Update Guidance — raspberry_pi_hailo_ai_services

Prepared 2026-10-31 for the VS Code GitHub Copilot agents updating
[gregm123456/raspberry_pi_hailo_ai_services](https://github.com/gregm123456/raspberry_pi_hailo_ai_services)
and the Raspberry Pi itself. Goal: adopt as many of this week's new Hailo
features as possible, and surface the new model types in the Gradio dashboard.

## Model selection preference

When proposing new models for this system, prioritize models in the
Hailo-supported universe (Hailo Model Zoo, Hailo applications, and models
verified for the Hailo-10H/runtime in use). If a potentially useful model is
outside that ecosystem, present it to Greg as an option and wait for his
decision before downloading, adapting, or integrating it.

## 1. Project context (do not change)

- **Hardware:** Raspberry Pi 5 + Raspberry Pi AI HAT+ 2 (Hailo-10H, 13 TOPS),
  Raspberry Pi OS Trixie (Debian 13), Hailo installed via the `hailo-all` apt package.
- **Core architecture (must be preserved):** the Hailo-10H exposes a single
  inference context (VDevice). A custom **device manager** holds the exclusive
  VDevice and serializes inference requests from services over a Unix socket
  (`/run/hailo/device.sock`). Services are lightweight clients; they must NOT
  open their own VDevice. Model caching lives in Hailo VRAM.
- **Existing services** (systemd services with REST APIs):

  | Service | Model / purpose | Port |
  |---|---|---|
  | hailo-clip | Zero-shot image classification | 5000 |
  | hailo-vision | Vision-language model (Qwen2-VL-2B) | 11435 |
  | hailo-whisper | Speech-to-text (Whisper-Base) | 11437 |
  | hailo-ocr | Text detection + recognition | 11436 |
  | hailo-pose | Human pose estimation (YOLOv8) | 11440 |
  | hailo-depth | Monocular depth estimation | 11439 |
  | hailo-piper | Text-to-speech (Piper TTS) | 5003 |
  | hailo-ollama | LLM inference (Qwen2.5-1.5B) | 11434 |

  **Exception:** `hailo-ollama` uses a precompiled binary that does not support
  the device-manager architecture. It requires exclusive device access and
  cannot run concurrently with the other services. Do not try to force it
  through the device manager.
- **Draft / experimental services:** `hailo-face` (face detection + embedding
  comparison), `hailo-scrfd` (specialized face detection), `hailo-florence`
  (vision understanding / captioning; installer done, HEFs need Hailo-10H
  recompilation).
- **Gradio web portal:** unified UI for testing/monitoring all services at
  `http://localhost:7860`.
- **Git submodules in this repo** (see `.gitmodules`):

  | Path | Upstream |
  |---|---|
  | `hailo-apps` | https://github.com/hailo-ai/hailo-apps |
  | `hailo-rpi5-examples` | https://github.com/hailo-ai/hailo-rpi5-examples |
  | `hailo_model_zoo` | https://github.com/hailo-ai/hailo_model_zoo |
  | `hailo_model_zoo_genai` | https://github.com/hailo-ai/hailo_model_zoo_genai |
  | `hailort` | https://github.com/hailo-ai/hailort |

- **Before starting:** `git pull` latest `main` first — the repo was updated
  on 2026-10-31, so do not assume the local checkout matches origin.

## 2. Upstream updates to adopt (week of Oct 26–31, 2026)

All versions below were verified against the GitHub API on 2026-10-31.
Publish dates are the release `published_at` timestamps.

### 2.1 HailoRT v5.5.0 — published 2026-10-28

- Releases: https://github.com/hailo-ai/hailort/releases
- What it is: runtime + PCIe driver + firmware for the Hailo-10H.
- **Release notes are empty** (release body length 0, verified via API).
  There is no published changelog for what changed inside v5.5.0. Do not
  invent changes; verify behavior empirically after upgrading.
- Action: bump the `hailort` submodule to tag `v5.5.0`.

### 2.2 Hailo Model Zoo (vision) v5.5.0 — published 2026-10-31

- Releases: https://github.com/hailo-ai/hailo_model_zoo/releases
- 16 new models, plus new variants of existing models. Updated for Dataflow
  Compiler v5.5.0 and HailoRT v5.5.0.
- Action: bump the `hailo_model_zoo` submodule to tag `v5.5.0`, and fetch
  the new HEF files for the models listed in §4.

New models in v5.5.0:

| Model | What it does | Notes |
|---|---|---|
| STARK-Lightning (`stark_lightning_repvgg_a0`) | Single-object tracking | First tracker in the Model Zoo |
| MiVOLO (`mivolo_d1`) | Age + gender estimation | 6-channel face+person input; face-only and body-only modes |
| YamNet (`yamnet`) | Audio classification | First audio model in the Zoo; 521-class AudioSet event classifier |
| YOLO26-seg-semantic | Cityscapes semantic segmentation | 1024×2048 input, 19 classes |
| CABiNet (`cabinet_mnv3l_uavid`) | Aerial (UAV) semantic segmentation | UAVid, 8 classes |
| PaddleOCR-v6 | Text detection + recognition | Complete PP-OCRv6 pipeline |
| all-MiniLM-L6-v2 | Sentence embeddings | First sentence-embedding model; 128-token input, 384-dim embeddings |
| DINOv2 (`dinov2_vits14_lc`) | Self-supervised ViT backbone + ImageNet linear classifier | ViT-S/14, 224×224 |
| PIDNet | Real-time Cityscapes segmentation | Three-branch pure-conv design |
| SPAN / SPANF | Efficient super-resolution | NTIRE 2024 / 2025 winners |
| PP-LiteSeg (`pp_liteseg_t`, `pp_liteseg_b`) | Real-time Cityscapes segmentation | PaddleSeg, STDC encoder |
| BiSeNetV2 (`bisenetv2`) | Real-time Cityscapes segmentation | 3.36M parameters |
| DDRNet | Real-time Cityscapes segmentation | Dual-resolution + DAPPM context head |
| ByteTrack | Multi-object pedestrian tracking | Associates every detection box, including low-score ones |
| ZipDepth (`zipdepth_256x832`, `zipdepth_384x384`) | Zero-shot monocular depth estimation | Lightweight |

New variants of existing models:

- YOLO26-seg-semantic aerial — YOLO26 segmentation fine-tuned on aerial imagery
- YOLOv11-seg — instance-segmentation variants of the YOLOv11 family
- YOLO26 — `yolo26s_768_448`, `yolo26s_768_576`, `yolo26x_seg`
- YOLO-World — `yolo_world_v2m`, medium open-vocabulary detector
- SCRFD — `scrfd_2.5g_384_640`, `scrfd_10g_384_640` (384×640 face detectors)

Minor: the DIV2K super-resolution network `real_esrgan_x2` now calibrates on
a DIV2K train-split set instead of the validation split.

### 2.3 GenAI Model Zoo — check the pinned version (no release this week)

- Releases: https://github.com/hailo-ai/hailo_model_zoo_genai/releases
- Latest release is **v5.4.0, published 2026-09-16** (release notes also
  empty). This is newer than the v5.3.0 that the project's watch baseline
  tracks — the changelog on the repo HEAD appears to lag the release tag.
- Action: check which version the `hailo_model_zoo_genai` submodule is pinned
  to; if it is behind v5.4.0, bump it to `v5.4.0` and re-check that the
  Qwen2-VL-2B / Qwen2.5-1.5B HEFs used by `hailo-vision` and `hailo-ollama`
  still match.

### 2.4 No action needed this week

- `hailo-apps` — latest release 26.10.0 (Oct 5, 2026). No update this week.
- `hailo-rpi5-examples` — latest release 25.7.0 (July 2025). No update.
- Dataflow Compiler v5.5.0 is referenced by the Model Zoo v5.5.0 release,
  but it is only distributed through Hailo's login-gated Developer Zone —
  there is no public release to download. Do not attempt to fetch it from
  GitHub.

## 3. Raspberry Pi update steps

1. Record the current state first: `hailortcli --version`,
   `dpkg -l | grep hailo`, and the currently pinned submodule commits
   (`git submodule status`).
2. `sudo apt update`, then check whether a `hailo-all` 5.5.0 package is
   available in the apt repo. **A GitHub tag does not mean the Debian
   package is published yet.** If apt still offers only 5.4.0, stop the
   runtime upgrade there, note it in the PR/commit message, and continue with
   the Model Zoo steps that do not require the new runtime — but verify HEF
   compatibility first (see step 4).
3. If `hailo-all` 5.5.0 is available: install it, reboot if the installer
   requires it, and confirm the driver/firmware report 5.5.0
   (`hailortcli fw-control identify` or equivalent).
4. **HEF / runtime compatibility check (important):** Model Zoo v5.5.0 HEFs
   are built for Dataflow Compiler v5.5.0 / HailoRT v5.5.0. Before replacing
   any HEF in a service, confirm the HEF loads against the installed
   runtime. If the runtime is still 5.4.0, test one new HEF explicitly and
   record the result; do not silently swap HEFs that fail to load.
5. For every HEF, confirm it targets **Hailo-10H** (not Hailo-8/8L — the
   Zoo ships both, and 8/8L-only releases must not be installed).
6. After the runtime and HEFs are in place, restart the device manager and
   each service, then run the repo's `test_services.sh` / `test_services.py`.
   Confirm: all services start, the device manager still serializes requests
   (no `HAILO_OUT_OF_PHYSICAL_DEVICES` errors), and the Gradio portal loads.

## 4. Repo update steps

1. Bump submodule pins: `hailort` → `v5.5.0`, `hailo_model_zoo` →
   `v5.5.0`, and `hailo_model_zoo_genai` → `v5.4.0` if it is behind.
   Commit the updated submodule pointers with a clear message.
2. Update version references in docs and install scripts
   (`system_setup/`, `README.md`, service `install.sh` files) from 5.4.0 to
   5.5.0 wherever they pin the HailoRT / Model Zoo version.
3. Update the model registry / model lists used by the device manager and
   services to include the new v5.5.0 models (§2.2).
4. Do not change the device-manager architecture, the Unix-socket API, or
   the service port assignments. Do not route `hailo-ollama` through the
   device manager.

## 5. Gradio dashboard — add the new model types

Prioritized by fit with the existing services. New services must follow the
existing pattern: device-manager client (no direct VDevice), systemd unit,
REST API, and a Gradio tab.

### High priority

1. **New audio-classification service/tab (YamNet)** — the first audio model
   in the Zoo. New service (e.g. `hailo-audio`): upload or record a short
   audio clip, return the top AudioSet event classes with scores. This is a
   new modality for the dashboard, alongside the existing Whisper
   speech-to-text service.
2. **Promote `hailo-face` from draft (MiVOLO + SCRFD)** — add a face tab:
   detect faces (SCRFD `scrfd_2.5g_384_640` / `scrfd_10g_384_640`),
   then estimate age and gender per face with MiVOLO (`mivolo_d1`). Show
   per-face crops with the estimated age and gender scores. Note MiVOLO
   takes face+person input and has face-only / body-only modes — wire the
   inputs accordingly.
3. **Upgrade `hailo-ocr` to PaddleOCR-v6** — replace the text detection +
   recognition pipeline with the complete PP-OCRv6 pipeline from v5.5.0 and
   expose it in the existing OCR tab.
4. **ZipDepth held back** — both published variants are Hailo-15H-only, so
   they are not candidates for this Hailo-10H system. Keep the existing
   `hailo-depth` models and UI unchanged.

### Medium priority

5. **Tracking service/tab (STARK-Lightning + ByteTrack)** — completed; see
   §9 for live USB-camera and uploaded-video tests and current limitations.
6. **Segmentation options** — expose the new Cityscapes segmentation models
   (YOLO26-seg-semantic, PIDNet, DDRNet, BiSeNetV2, PP-LiteSeg) as a model
   selector in a segmentation view, with per-pixel class overlays (19
   Cityscapes classes). CABiNet adds an aerial-imagery variant.
7. **YOLO-World v2m open-vocabulary detection** — a text-prompt detection
   tab (type a class name, get boxes), complementing the zero-shot CLIP tab.

### Lower priority / nice to have

8. **DINOv2** as an embedding/backbone option in the CLIP/vision area.
9. **all-MiniLM-L6-v2** sentence embeddings — a small text-embedding
   endpoint/tab (384-dim vectors).
10. **SPAN / SPANF super-resolution** — an image upscaling tab (note the
    DIV2K calibration change for `real_esrgan_x2` if that model is also
    refreshed). SPANF x4 service and portal tab are deployed and live-tested;
    see §8.

## Progress notes (2026-10-31)

- The Raspberry Pi OS/Hailo 5.5.0 plan is complete. After Greg rebooted,
  Vision produced distinct, image-appropriate results for three test images.
- In this repository worktree, submodule checkouts are now at `hailort`
  v5.5.0, `hailo_model_zoo` v5.5.0, and `hailo_model_zoo_genai` v5.4.0;
  the parent gitlinks are updated but not committed.
- Active HailoRT wheel and direct-driver setup references in service install
  scripts now point to the 5.5.0 public Hailo-10 downloads.
- **Excluded as incompatible:** the v5.5.0 Model Zoo configs declare
  both ZipDepth variants (`zipdepth_256x832`, `zipdepth_384x384`) as
  `hailo15h` only, not Hailo-10H. YamNet's config does include `hailo10h`.
  Therefore ZipDepth cannot be added to this Pi based on the published model
  config; no H10 HEF or Developer Zone compiler should be assumed available.
  Per Greg's direction, skip ZipDepth completely; preserve existing depth
  models and their UI. Continue only with offerings verified for Hailo-10H.
- Verified public v5.5.0 Hailo-10H HEFs (HTTP 200): YamNet, MiVOLO, SCRFD,
  PaddleOCR-v6 tiny, YOLO-World v2m, YOLO26 semantic, PIDNet, DDRNet,
  BiSeNetV2, CABiNet, STARK-Lightning, ByteTrack tiny, DINOv2, all-MiniLM,
  and SPANF. YamNet HEF metadata reports compiler 5.5.0 and HAILO10H.
- Other exclusions from the offered set: ZipDepth, ByteTrack nano, and
  YOLO26x-seg are Hailo-15H-only. Both `pp_liteseg_b` and `pp_liteseg_t` are
  present and include Hailo-10H support. Keep existing services/models
  unchanged where no Hailo-10H replacement is published.
- Face-model implementation check: the existing `hailo-face` and `hailo-scrfd`
  wrappers still contain mock/fallback detections and placeholder inference;
  they cannot be promoted as real Hailo functionality as-is. Downloaded the
  public v5.5.0 Hailo-10H SCRFD 2.5g 384x640 and MiVOLO D1 HEFs (no Developer
  Zone download was needed) and verified both parse as HAILO10H / compiler
  5.5.0. Added a generic tensor-inference handler to the Device Manager.
- Added the SCRFD output decoder/NMS, MiVOLO face-only preprocessing, a new
  `/v1/attributes` route, an installer for the two public HEFs, and the portal
  Face tab. Four tensor-handler tests pass under the Device Manager's HailoRT
  5.5.0 venv, and six face pipeline/route tests pass. The manager handler and
  corrected unbatched SCRFD/MiVOLO inputs are deployed. Live SCRFD inference
  on a blank image returned a valid empty result; direct MiVOLO inference on a
  synthetic face-only tensor returned three outputs. A full non-empty face
  image evaluation remains pending.
- **Face portal deployed:** the live Gradio config includes the Face tab and
  260 components. The deployed `HailoFaceClient` called `/v1/attributes` and
  received a valid empty result for a blank image. The SCRFD and MiVOLO model
  paths both ran on Hailo-10H; representative face-image accuracy remains
  unverified.
- YamNet service and Audio tab code are in `system_services/hailo-audio/` and
  the web portal. Five isolated tests pass; the Gradio app builds; the H10 HEF
  parses with HailoRT 5.5.0. Deployment initially exposed a shared socket
  permission mismatch: the socket group was `root`, while the service clients
  use dedicated accounts. With Greg's approval, coordinated Device Manager
  client access was configured by setting
  `HAILO_DEVICE_SOCKET_GROUP=hailo-device-mgr` and adding the Device Manager
  client group to the CLIP, Depth, Pose, Vision, OCR, Whisper, and Audio service
  units. The socket now has mode `0660` and group `hailo-device-mgr`; Vision
  restarted and returned healthy.
- **YamNet live deployment passed:** enabled `hailo-audio.service`; `/ready`
  reports `{"status":"ready","model":"yamnet"}`. A generated 3-second, 16 kHz
  440 Hz WAV classified through `/v1/classify` with five predictions (top
  result: “Dial tone”, score 0.91; 42.92 ms inference). This verifies live
  H10 inference and the REST response shape, but is only a synthetic-audio
  smoke test, not a representative recording evaluation.
- **Portal Audio tab deployed:** copied the updated portal app, client, and
  service-manager files into `/opt/hailo-web-portal` and restarted the portal.
  The live Gradio config includes the YamNet tab and its controls; the Audio
  tab is visible in the browser. A WAV upload through the live Gradio
  `classify_audio` API returned five predictions and the performance summary;
  the deployed `HailoAudioClient.classify()` and service REST paths also pass.
  Manual browser microphone interaction remains untested.
- **Restart workaround:** the Device Manager's old process did not exit within
  systemd's stop timeout and was force-killed before systemd started the new
  process successfully. The new manager and socket are healthy, with no failed
  units. Greg approved continuing the YamNet test; investigate if the manager
  shutdown timeout recurs.
- **5.5.0 binding audit and cleanup:** verified HailoRT runtime, PCIe driver,
  firmware, Tappas core, and the Device Manager/other HailoRT-dependent service
  venvs at 5.5.0. The Raspberry Pi apt repository's `python3-hailort` 4.23.0
  and `python3-hailo-tappas` 5.1.0 bindings could not load against the current
  runtime and had no active service consumers; removed those packages and the
  residual GenAI Zoo 5.2.0 package config. Removed Greg's stale user-local
  HailoRT 5.3.0 wheel without bypassing PEP 668. The GenAI Model Zoo submodule
  remains at v5.4.0 because that is its latest release; HailoRT 5.5.0 does not
  imply a nonexistent GenAI Zoo v5.5.0.
- Updated the system setup guide and service guidance to keep HailoRT bindings
  inside isolated project/service venvs; the YamNet installer no longer uses
  `--system-site-packages`. Re-running the installer is not required for the
  already-running Audio service, which is a device-manager client and does not
  import HailoRT directly.
- The system Python environment does not include pytest, so focused
  `unittest` cases and direct HTTP/client checks were used instead. The
  Device Manager tests pass with its matching HailoRT 5.5.0 venv. No
  `--break-system-packages` install was performed.
- **PaddleOCR-v6 held back safely:** both tiny Hailo-10H v5.5.0 HEFs are
  publicly reachable, and the Model Zoo config declares detection input
  `544x960x3`, recognition input `48x320x3`, and recognition output
  `1x40x6906`. However, its configured
  `ppocrv6_tiny_char_dict.npz` URL returns HTTP 403. The current service
  decoder is for a much smaller legacy character set, and the official
  PaddleOCR `ppocr_keys_v1.txt` alternative has only 6,623 entries. That does
  not match the HEF's 6,906 classes, so substituting it would produce incorrect
  text. The existing OCR HEFs, service, and API are unchanged; skip this item
  unless the exact class mapping becomes publicly available.

## 6. Verification checklist

- [x] `git submodule status` checkouts are exactly tagged `hailort` @ v5.5.0, `hailo_model_zoo` @
      v5.5.0, `hailo_model_zoo_genai` @ v5.4.0 (or documents why not).
- [x] Pi reports HailoRT, driver, and firmware 5.5.0.
- [x] YamNet HEF loads and returns live `/v1/classify` results on Hailo-10H.
- [ ] Every new HEF loads against the installed runtime and targets Hailo-10H.
      YamNet, SCRFD, MiVOLO, SPANF x4, STARK, and ByteTrack have loaded live;
      other planned HEFs remain pending. PaddleOCR-v6 is held back because the
      matching 6,906-class decoder dictionary could not be obtained.
- [ ] Device manager + all services start; `test_services.sh` /
      `test_services.py` pass; no `HAILO_OUT_OF_PHYSICAL_DEVICES` errors.
- [ ] Gradio portal at :7860 shows the new tabs/options from §5 and each
      one returns results end-to-end. Audio and Face tabs are deployed and
      smoke-tested. Super Resolution is deployed and live-tested at 512x512,
      1024x1024, and 700x500. Tracking is deployed and smoke-tested for both
      modes and both camera and upload routes; other planned tabs remain
      pending.
- [ ] `hailo-ollama` still works standalone (exclusive access unchanged).
- [x] README / install docs updated for HailoRT 5.5.0 and isolated bindings.

## 7. Known unknowns (do not guess — verify or record as unknown)

- HailoRT v5.5.0 and GenAI Zoo v5.4.0 both shipped with **empty release
  notes**; nothing is published about what changed inside them. If behavior
  differs after upgrading, record the observed difference rather than
  assuming a cause.
- Whether the `hailo-all` 5.5.0 apt package is published yet (check on the
  Pi; GitHub tags do not guarantee apt availability).
- Dataflow Compiler v5.5.0 availability for recompiling any custom HEFs
  (login-gated Developer Zone only).

## 8. SPANF x4 implementation progress

- Added and deployed a standalone `hailo-super-resolution` service using the
  public v5.5.0 Hailo-10H SPANF x4 HEF (602,112 bytes).
- The service processes arbitrary aspect ratios as overlapping 512x512 tiles,
  blends tile boundaries, and returns exact 4x dimensions. Inputs are capped at
  4 megapixels to bound RAM; 512x512, 1024x1024, and non-square sizes are
  covered by unit tests.
- Added the portal client/tab, service manager entry, installer, systemd unit,
  and service/API/architecture/troubleshooting documentation.
- Unit/API tests, Python compilation, `bash -n`, and `git diff --check` pass.
  The service is enabled, `/health` and `/health/ready` return successfully,
  and the live portal reports the tab and service.
- **HEF permission workaround:** the first live request failed because the
  Device Manager, not the API service, opens the HEF. The model was initially
  beneath a private service-owned directory. The installer now creates the
  state/model directories as `root:hailo-device-mgr` mode `0750`, and the HEF
  as `root:hailo-device-mgr` mode `0640`; the unit no longer uses
  `StateDirectory=` so systemd cannot reset those shared-read permissions.
- Live SPANF results: 512x512 -> 2048x2048 (1 tile, 1,091.51 ms);
  1024x1024 -> 4096x4096 (9 tiles, 7,423.59 ms); 700x500 -> 2800x2000
  (2 tiles). All returned valid RGB images at exact 4x dimensions.
- The Device Manager reached seven cached networks after the SPANF load, with
  zero LRU evictions, no runtime errors, and Hailo temperature below 48°C.
- Final live check after all three image tests: Device Manager still reports
  seven networks, zero LRU evictions, and no broken runtime; the SPANF service,
  Device Manager, and portal are active, and `/health` plus `/health/ready`
  return healthy responses. The Pi had 3.4 GiB available RAM and the Hailo
  temperature was 48.8°C.
- The journal records the portal's service-control account issuing
  `systemctl stop hailo-vision` at 15:19:05 PDT. This was separate from the
  SPANF tests; Vision was left stopped and was not restarted by this work.

## 9. STARK + ByteTrack tracking integration

- Added the `hailo-tracking` aiohttp service, systemd unit, idempotent
  installer, pinned venv requirements, REST/API/architecture/troubleshooting
  docs, portal client and Tracking tab, and Device Manager service-control
  integration. The public Model Zoo v5.5.0 Hailo-10H HEFs are installed under
  `/var/lib/hailo-tracking/models`; no Developer Zone downloads were needed.
- STARK has two named HEF inputs (`128x128x3` template and `320x320x3`
  search); ByteTrack Tiny has one `608x1088x3` input and nine outputs. Updated
  the Device Manager tensor handler to configure named multi-input HEFs. The
  first live attempt exposed that the deployed manager was stale; its source
  was synchronized and its seven tensor-handler tests pass in the matching
  HailoRT 5.5.0 venv.
- The manager restart took five minutes because the old process did not exit
  after SIGTERM; systemd killed it at the stop timeout, then started the new
  manager. It is active. The restart cleared the model cache; YamNet reloaded
  on demand. This is the previously observed shutdown-timeout workaround,
  not a tracker-model failure.
- A second live failure found that the HEFs expect unbatched input dimensions.
  Removed the leading batch axis for STARK and ByteTrack, added shape
  regression tests, and deployed the fix.
- The USB camera reports 15 FPS but capture measurements were about 2 FPS.
  USB clips now stage bounded JPEG frames and encode at the captured frame
  count divided by requested duration, preventing camera startup or the
  reported/actual FPS mismatch from shortening the resulting clip. USB
  staging is capped at 64 MiB, 600 frames, and 8 megapixels per frame.
- Live smoke tests passed:
  - USB camera, one-second capture at 640x480: STARK processed 4 frames
    (42 ms total inference, one track); ByteTrack processed 4 frames
    (237 ms total inference, zero pedestrian detections in the test scene).
  - Uploaded synthetic 4-frame 320x240 MP4: STARK returned a valid MP4
    (46 ms total inference); ByteTrack returned a valid MP4 (310 ms total
    inference, zero detections in the synthetic scene).
  - Both HEFs are now cached with YamNet, with zero LRU evictions and no
    runtime-broken reason. The tracker, manager, and portal are active; the
    live Gradio config includes the Tracking tab (303 components).
- Sixteen tracker pipeline/API tests and three portal-client tests pass; the
  Gradio app builds. The smoke tests confirm the request/response path and
  tensor dimensions, not representative pedestrian-detection or long-term
  tracking accuracy. CSI camera capture remains unverified because no CSI
  camera is connected.
