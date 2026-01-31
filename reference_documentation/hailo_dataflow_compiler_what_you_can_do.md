# What You Can Do with the Hailo Dataflow Compiler (v5.2.0)

This summary distills the intended and supported uses described in the Hailo Dataflow Compiler v5.2.0 user guide. It is meant as a quick, practical reference for what you can build and how far the toolchain goes.

## Core Intended Use (Vision / Classic DL)
The Dataflow Compiler is designed to:
- **Translate** trained models (ONNX or TFLite) into Hailo’s internal representation (HAR).
- **Optimize** models (quantization, calibration, compression, optional model-script modifications).
- **Compile** optimized models into **HEF** binaries for deployment on Hailo hardware.
- **Deploy** HEF on target devices via **HailoRT** (C/C++ or Python APIs).

Supported inputs:
- **ONNX** models (opset 21 supported)
- **TensorFlow Lite** (recommended for TF2.x workflows)

Deprecated inputs:
- TensorFlow 1.x/2.x checkpoints or frozen graphs via parser APIs are deprecated; use TFLite instead.

## Intended Model Build Workflow
1. **Parse** (ONNX/TFLite → HAR)
2. **Optimize** (calibration + quantization + optional model scripts)
3. **Compile** (HAR → HEF)
4. **Run** inference with HailoRT

Supporting tools:
- **Profiler**: performance and layer breakdown analysis
- **Emulator**: native / fp_optimized / quantized inference simulation
- **Accuracy analysis**: layer noise/SNR inspection

## Model Script Support (Intended Customization)
Model scripts are an intended, supported way to modify the graph and optimization behavior. Common uses include:
- **Input normalization**
- **Input format conversions** (e.g., YUY2 → YUV → RGB; some conversions not emulated)
- **On-chip resize**
- **Postprocessing insertion** (e.g., NMS for supported meta-architectures)
- **Optimization tuning** (compression level, optimization level, calibration settings)
- **Quantization tweaks** (e.g., precision for specific output layers)

## GenAI (Preview, LoRA-Only)
GenAI support exists but is **limited and specialized**:
- **Supported path**: compile **LoRA adapters** onto **pre-optimized Hailo HARs**.
- **Not supported**: full end-to-end compilation of arbitrary LLMs or diffusion models from raw PyTorch/ONNX.
- **Supported targets**: Hailo-10H (per guide notes and tutorials).

The GenAI flow in v5.2.0 is:
1. Start with a **pre-optimized HAR** provided by Hailo (not user-generated from raw model).
2. Load **LoRA weights** (safetensors).
3. Run **optimize** (LoRA-only path).
4. Compile to **HEF**.

### LoRA Constraints (from tutorial)
- LoRA parameters are limited (e.g., rank and alpha constraints in the example).
- LoRA training uses common HF/PEFT tooling but compilation requires the Hailo-provided HAR + scripts.

## Supported Hardware Targets
- **Hailo-10H** (use `hw_arch=hailo10h`)
- **Hailo-15H / Hailo-15L** (use `hw_arch=hailo15h` or `hw_arch=hailo15l`)

## What This Means for Alternate Ollama-Compatible / SD Models
- **Raw LLM/SD checkpoints** are **not directly compiled** with DFC.
- You need **Hailo-provided, pre-optimized HARs** for the specific model family.
- Your allowed customization is **LoRA adapters** on top of those base HARs.

## Intended Deployment Use
- Use **HailoRT** on the target device to load and run HEF.
- HailoRT supports runtime inference (sync and async) with C/C++ and Python.

## Practical Checklist
If your model is a **classic vision model**:
- Provide ONNX or TFLite
- Prepare calibration dataset
- Use DFC parse → optimize → compile
- Deploy HEF with HailoRT

If your model is **GenAI (LLM/SD)**:
- Obtain **Hailo-provided base HAR + .alls scripts**
- Prepare **LoRA weights**
- Use DFC LoRA flow to optimize + compile
- Deploy HEF with HailoRT

---

This file is a condensed, intent-focused view of the official guide. It does not replace the full user guide, especially for detailed APIs and edge cases.