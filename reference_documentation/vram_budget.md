# Hailo-10H VRAM Budget per Service

**Hardware:** Raspberry Pi AI HAT+ 2 (Hailo-10H NPU) — 8 GB dedicated VRAM

---

## Model Sizes and Estimated VRAM Usage

HEF files are compressed binary bundles (weights + network graph). At runtime, the Hailo driver
expands them into VRAM: weights are decompressed and activation/buffer memory is allocated around
them. The Hailo SDK provides no per-model VRAM query API at the time of writing, so the estimates
below are derived from HEF disk size and known parameter counts where available.

| Service | HEF file(s) | HEF size on disk | VRAM estimate | HEF count | Notes |
|---|---|---|---|---|---|
| **hailo-vision** | `Qwen2-VL-2B-Instruct.hef` | **2.2 GB** | **~4–5 GB** | 1 | 2B-parameter VLM; HEF is compressed, weights expand to fp16 in VRAM |
| **hailo-whisper** | `Whisper-Base.hef` | 131 MB | ~200–400 MB | 1 | Transformer encoder+decoder for ASR |
| **hailo-clip** | `clip_vit_b_32_image_encoder.hef` + `clip_vit_b_32_text_encoder.hef` | 78 MB + 78 MB = **156 MB** | ~300–500 MB | 2 | Two HEFs loaded as one logical model entry in device manager |
| **hailo-depth** | `scdepthv3.hef` | 12 MB | ~20–50 MB | 1 | Lightweight depth estimation CNN |
| **hailo-pose** | `yolov8s_pose.hef` | 18 MB | ~30–60 MB | 1 | YOLOv8s pose — small variant |
| **hailo-ocr** | `ocr_det.hef` + `ocr.hef` | 7.1 MB + 7.0 MB = **14 MB** | ~20–50 MB | 2 | Detection + recognition, both small |
| **hailo-piper** | *(ONNX — CPU only)* | — | **0 MB** | 0 | Piper TTS runs on Pi CPU via ONNX Runtime; no NPU VRAM consumed |
| **hailo-florence** *(experimental)* | `florence2_transformer_encoder.hef` + `florence2_transformer_decoder.hef` | 46 MB + 97 MB = **143 MB** | ~300–500 MB | 2 | Currently requires Hailo-10H HEF recompilation; not production-ready |
| **hailo-ollama** *(exception)* | *(binary, not device-manager)* | — | **exclusive device** | — | Uses its own VDevice; cannot coexist with any other service |

**HEF file locations:**

| Service | Path |
|---|---|
| hailo-clip | `/usr/local/hailo/resources/models/hailo10h/clip_vit_b_32_{image,text}_encoder.hef` |
| hailo-vision | `/var/lib/hailo-vision/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef` |
| hailo-whisper | `/var/lib/hailo-whisper/resources/models/hailo10h/Whisper-Base.hef` |
| hailo-depth | `/var/lib/hailo-depth/resources/models/scdepthv3.hef` |
| hailo-pose | `/var/lib/hailo-pose/resources/models/hailo10h/yolov8s_pose.hef` |
| hailo-ocr | `/var/lib/hailo-ocr/resources/models/hailo10h/ocr_{det,}.hef` |

---

## Key Constraint: hailo-vision Dominates the Budget

The Qwen2-VL-2B model is a 2-billion-parameter vision-language transformer. Its 2.2 GB HEF
expands to roughly 4–5 GB in VRAM after decompression and buffer allocation, consuming **50–65%
of total available VRAM** on its own.

All other production services combined (whisper + clip + depth + pose + ocr) total only
~331 MB of HEF and fit comfortably in the remaining budget.

---

## Empirical Concurrency Findings

The following combinations have been tested on this system:

| Service Combination | Result | Notes |
|---|---|---|
| vision + depth + pose + ocr + whisper (5 NPU services) | ✅ Fits | Confirmed working |
| vision + depth + pose + ocr + whisper + clip (6 NPU services) | ❌ RESOURCE_EXHAUSTED | Confirmed failing — adding clip's 2 HEFs after the above 5 are loaded exceeds VRAM |
| clip + depth + pose + ocr + whisper (5 NPU services, no vision) | ✅ Fits | 331 MB total HEF — trivially fits |
| Any single service | ✅ Fits | All individual services fit |

**Root cause of RESOURCE_EXHAUSTED:** hailo-vision + hailo-whisper + hailo-depth + hailo-pose +
hailo-ocr already consume ~4.5–5.5 GB of VRAM estimated. Adding hailo-clip's two additional HEFs
(~300–500 MB VRAM) pushes the total over the 8 GB limit when accounting for runtime overhead and
Hailo driver reserved memory.

---

## Recommended Service Subsets

Choose the subset that matches the use-case. hailo-piper (CPU-only) can always be added without
affecting NPU VRAM.

### Subset A — "Vision-centric stack" (recommended for visual AI applications)
Includes the VLM, depth, pose, and text overlays. Drops CLIP and Whisper.

| Service | VRAM est. |
|---|---|
| hailo-vision | ~4–5 GB |
| hailo-depth | ~30–50 MB |
| hailo-pose | ~30–60 MB |
| hailo-ocr | ~20–50 MB |
| hailo-piper | 0 MB (CPU) |
| **Total** | **~4.1–5.2 GB** |

### Subset B — "Multimodal stack" (CLIP + audio, no VLM)
Drops hailo-vision. All other production services run concurrently.

| Service | VRAM est. |
|---|---|
| hailo-clip | ~300–500 MB |
| hailo-whisper | ~200–400 MB |
| hailo-depth | ~30–50 MB |
| hailo-pose | ~30–60 MB |
| hailo-ocr | ~20–50 MB |
| hailo-piper | 0 MB (CPU) |
| **Total** | **~580 MB – 1.1 GB** |

### Subset C — "VLM + audio"
VLM with voice I/O. Drops vision sensors (depth, pose, OCR).

| Service | VRAM est. |
|---|---|
| hailo-vision | ~4–5 GB |
| hailo-whisper | ~200–400 MB |
| hailo-piper | 0 MB (CPU) |
| **Total** | **~4.2–5.4 GB** |

### Subset D — "Full minus VLM minus clip" (5 small NPU services)
All lightweight services. Frees maximum VRAM for future models.

| Service | VRAM est. |
|---|---|
| hailo-whisper | ~200–400 MB |
| hailo-depth | ~30–50 MB |
| hailo-pose | ~30–60 MB |
| hailo-ocr | ~20–50 MB |
| hailo-piper | 0 MB (CPU) |
| **Total** | **~280–560 MB** |

---

## Starting a Specific Subset

```bash
# Subset A — vision-centric
sudo systemctl stop hailo-clip hailo-whisper
sudo systemctl start hailo-vision hailo-depth hailo-pose hailo-ocr hailo-piper

# Subset B — multimodal (no VLM)
sudo systemctl stop hailo-vision
sudo systemctl start hailo-clip hailo-whisper hailo-depth hailo-pose hailo-ocr hailo-piper

# Subset C — VLM + audio
sudo systemctl stop hailo-clip hailo-depth hailo-pose hailo-ocr
sudo systemctl start hailo-vision hailo-whisper hailo-piper

# Verify what is loaded
curl -s http://127.0.0.1:5099/v1/device/status | python3 -m json.tool
```

**Always restart hailo-device-manager when switching between subsets that include hailo-vision**
to flush VRAM cleanly:

```bash
sudo systemctl restart hailo-device-manager
sudo systemctl start hailo-<service>  # for each desired service
```

---

## When You See HAILO_RESOURCE_EXHAUSTED

This error from the device manager means the combined VRAM of already-loaded models left
insufficient room for the new model being requested.

**Diagnosis:**
```bash
curl -s http://127.0.0.1:5099/v1/device/status | python3 -m json.tool
# Check "loaded_networks" — identify which large models are loaded
```

**Fix — choose a subset that fits:**
```bash
# Stop the highest-VRAM service (usually hailo-vision)
sudo systemctl stop hailo-vision
sudo systemctl restart hailo-device-manager
sudo systemctl start hailo-clip   # or whichever service was failing
```

**Long-term fix** — LRU eviction is implemented in the device manager. When VRAM is full,
it automatically evicts the least-recently-used model and retries the load. No manual service
stopping is needed. See [Device_Manager_LRU_eviction_plan.md](../Device_Manager_LRU_eviction_plan.md).

---

## Notes on Measurement Gaps

- **No per-model VRAM API**: Hailo SDK (5.3.0) does not expose a query for per-model VRAM
  consumption. The estimates above are derived from HEF disk size and model architecture knowledge.
- **Runtime overhead**: The Hailo driver reserves additional VRAM for DMA buffers, pipeline scratch
  space, and the VDevice context itself. This overhead is not reflected in the estimates above.
- **Model compression ratio**: CLIP ViT-B/32 and the small YOLO variants have lower compression
  ratios (~1.5–2×). The Qwen2-VL-2B VLM has a higher ratio (~2–2.5×) due to transformer weight
  tiling, explaining why its 2.2 GB HEF likely occupies 4–5 GB at runtime.
- If Hailo adds a VRAM measurement tool in a future SDK release, replace estimates here with
  measured values from `hailortcli` or the Python API.
