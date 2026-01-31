# Supported Image Classifiers & Vision Models

**Date:** January 31, 2026  
**Scope:** Comprehensive survey of image classification, image captioning, and visual understanding models available in git submodules

---

## Executive Summary

The included git submodules contain **significantly more than basic object detection** classifiers. Available models span:

- **Generative vision-to-text** (image captioning with arbitrary vocabulary)
- **Open-vocabulary zero-shot classification** (CLIP—unlimited text descriptions)
- **Multi-modal vision-language models** (VLMs—image + text → reasoning/generation)
- **Dense feature descriptors** (visual localization and image matching)
- **Traditional CNN classification** (reference: ImageNet 1000-class)

This enables rich semantic understanding of images with **arbitrary vocabulary** rather than fixed category lists.

---

## 1. Florence-2: Vision-to-Text Captioning

### Overview
Florence-2 is a generative vision model that produces **natural language descriptions** of images—rich, narrative captions with arbitrary vocabulary.

### Location
- **Primary Implementation:** `hailo-rpi5-examples/community_projects/dynamic_captioning/`
- **Model Files:** 
  - `florence2_transformer_encoder.hef` (Hailo-optimized)
  - `florence2_transformer_decoder.hef` (Hailo-optimized)
  - `vision_encoder.onnx` (ONNX reference)

### Architecture
- **Type:** Encoder-Decoder Transformer
- **Vision Encoder:** 
  - DaViT (Dual Attention ViT) for image feature extraction
  - Processes images into visual embeddings
  - Runs on ONNX (not Hailo-accelerated in current setup)
- **Text Encoder:** Hailo-accelerated, processes text embeddings
- **Decoder:** Hailo-accelerated transformer decoder for token generation
- **Tokenizer:** HuggingFace tokenizer (`tokenizer.json`)

### Capabilities
- **Image Captioning:** Generate descriptive captions of scenes, objects, and their relationships
- **Fine-grained description:** Can describe attributes, spatial relationships, and context
- **Arbitrary vocabulary:** Not limited to predefined classes—generates free-form English text

### Key Files
- [caption.py](../hailo-rpi5-examples/community_projects/dynamic_captioning/caption.py) - Full inference pipeline
- [README.md](../hailo-rpi5-examples/community_projects/dynamic_captioning/README.md) - Installation and usage

### Features
- Real-time caption generation on Raspberry Pi 5 with Hailo-10H
- Scene change detection using CLIP semantic similarity
- Text-to-speech output integration (espeak)
- Efficient encoder-decoder pipeline with async processing

### Example Use Cases
- Dynamic scene description for accessibility
- Automated video annotation
- Intelligent event trigger (caption only when scene changes significantly)
- Surveillance scene understanding

---

## 2. CLIP: Zero-Shot Image Classification

### Overview
OpenAI's CLIP model enables **open-vocabulary classification**—match images to arbitrary text descriptions without requiring training data for specific categories. Provides semantic understanding with rich vocabulary (not limited to 100 classes).

### Locations
- **Python Pipeline:** `hailo-apps/hailo_apps/python/pipeline_apps/clip/`
- **C++ Standalone:** `hailo-apps/hailo_apps/cpp/zero_shot_classification/`

### Architecture
- **Image Encoder:** CLIP ResNet-50x4 (640-dimensional embeddings)
- **Text Encoder:** CLIP text transformer (same 640-dimensional space)
- **Matching:** Dot-product similarity in shared embedding space
- **Post-processing:** Softmax normalization for confidence scores

### Models Used
- `clip_vit_base_patch32` (standard reference)
- Hailo-optimized HEF files for image encoder
- Pre-computed text embeddings and projection matrices

### Capabilities
- **Semantic classification:** Match images to arbitrary text descriptors
- **Zero-shot learning:** No task-specific training required
- **Multiple detection modes:**
  - Direct CLIP on full frames (scene classification)
  - Person detection + CLIP on crops (person attribute classification)
  - Face detection + CLIP on crops (facial attribute classification)
- **Runtime configurability:** Define/modify text prompts on-the-fly
- **Negative examples:** Contrastive text descriptors for improved discrimination

### Key Files
- [clip.py](../hailo-apps/hailo_apps/python/pipeline_apps/clip/clip.py) - Core pipeline
- [text_image_matcher.py](../hailo-apps/hailo_apps/python/pipeline_apps/clip/text_image_matcher.py) - Text embedding generation
- [README.md](../hailo-apps/hailo_apps/python/pipeline_apps/clip/README.md) - Comprehensive usage guide
- [clip_example.cpp](../hailo-apps/hailo_apps/cpp/zero_shot_classification/clip_example.cpp) - C++ implementation

### Features
- **GUI interface:** GTK-based controls for threshold, text entries, confidence visualization
- **Embedding persistence:** Save/load embeddings in JSON format
- **Ensemble mode:** Multiple template variations for robustness
  - "a photo of a {text}"
  - "a photo of the {text}"
  - "a photo of my {text}"
  - "a photo of a big {text}"
  - "a photo of a small {text}"
- **Batch processing:** Efficient inference with configurable batch sizes
- **Real-time video:** Processes camera feeds with interactive controls

### Example Descriptors
Instead of "shirt", you can use:
- "person wearing red shirt"
- "person carrying backpack"
- "smiling person"
- "person with beard"
- "person with glasses"
- "office room"
- "outdoor park"
- "kitchen"
- "empty shelf"
- "stocked shelf"

### Example Use Cases
- Retail inventory monitoring (custom visual searches)
- Security surveillance with natural language queries
- Content moderation with custom descriptors
- Smart home understanding ("person cooking", "person reading")
- Accessibility scene description

---

## 3. Vision-Language Models (VLMs): Qwen Series

### Overview
Multi-modal transformers that accept image + text input and generate rich descriptive or analytical text output. Enable image understanding, captioning, and visual question-answering with arbitrary prompts.

### Location
- **HailoRT Integration:** `hailort/hailort/libhailort/include/hailo/genai/vlm/`
- **Python Bindings:** `hailort/hailort/libhailort/bindings/python/`
- **Examples:** `hailort/hailort/libhailort/examples/genai/vlm_example/`
- **Hailo-apps Integration:** `hailo-apps/hailo_apps/python/gen_ai_apps/vlm_chat/`

### Available Models (HailoRT 5.2.0)
From `hailo_model_zoo_genai/docs/MODELS.rst`:

| Model | Parameters | Size | Context | Numerical Scheme |
|-------|-----------|------|---------|-----------------|
| Qwen2-VL-2B-Instruct | 2B | 2.18 GB | Dynamic | A8W4, symmetric, group-wise |
| Qwen2-VL-7B-Instruct | 7B | Variable | Dynamic | A8W4, symmetric, group-wise |
| Qwen3-VL-2B | 2B | Varies | Dynamic | A8W4, symmetric, group-wise |

### Architecture
- **Vision Encoder:** Processes images into visual embeddings
- **Language Model:** Transformer-based decoder (1.5B–7B parameters)
- **Tokenizer:** Hailo-optimized, runs on device
- **Token Generation:** Autoregressive text generation with configurable parameters

### Capabilities
- **Image captioning:** Generate descriptions with arbitrary vocabulary
- **Visual question-answering:** Answer questions about image content
- **Scene understanding:** Multi-modal reasoning about images + text
- **Free-form text generation:** Descriptive captions, analysis, narratives
- **Batch processing:** Efficient multi-image/multi-prompt inference
- **Context management:** Conversation history tracking with token limits

### Key Components
- **VLM Class:** `hailort::genai::VLM` (C++ API)
- **VLMGenerator:** Manages generation parameters and state
- **Frame Support:** Single images and video sequences
- **Temperature Control:** Adjustable sampling for output diversity
- **Token Limits:** Configurable max_generated_tokens

### Key Files
- [vlm.hpp](../hailort/hailort/libhailort/include/hailo/genai/vlm/vlm.hpp) - C++ API definition
- [vlm.cpp](../hailort/hailort/libhailort/src/genai/vlm/vlm.cpp) - Implementation
- [vlm_chat.py](../hailo-apps/hailo_apps/python/gen_ai_apps/vlm_chat/vlm_chat.py) - Interactive Python application
- [simple_vlm_chat.py](../hailo-apps/hailo_apps/python/gen_ai_apps/simple_vlm_chat/simple_vlm_chat.py) - Minimal example

### Features
- **Structured prompts:** JSON-based message Format with role/content pairs
- **Image references:** Placeholder support for multiple images in prompts
- **Video support:** Process image sequences (not just single frames)
- **Context persistence:** Save/load conversation state
- **Stop tokens:** Custom generation termination sequences
- **Recovery sequences:** Graceful handling of max-token termination

### Example Prompts
```json
{
  "role": "user",
  "content": [
    {"type": "image"},
    {"type": "text", "text": "Describe this image in detail"}
  ]
}
```

### Example Use Cases
- Real-time scene analysis and description
- Interactive visual Q&A systems
- Accessibility: Automatic image descriptions for visually impaired
- Content analysis and metadata generation
- Smart surveillance with semantic understanding

---

## 4. XFeat: Dense Feature Descriptors & Interest Point Detection

### Overview
XFeat is an efficient neural network that extracts **dense local feature descriptors** from images. Enables image matching, loop closure detection, and visual localization—useful for navigation and SLAM-like applications.

### Location
- **Reference:** `hailo-rpi5-examples/community_projects/Navigator/modules/model.py`
- **Application:** `hailo-rpi5-examples/community_projects/Navigator/`

### Architecture
- **Paper:** "XFeat: Accelerated Features for Lightweight Image Matching, CVPR 2024"  
  URL: https://www.verlab.dcc.ufmg.br/descriptors/xfeat_cvpr24/
- **Design:** Single efficient model combining:
  - Interest point detection (keypoint localization)
  - Descriptor extraction (feature vectors at keypoints)
- **Base Architecture:** CNN backbone with multi-scale processing
- **Output:**
  - Dense feature maps (B, 64, H/8, W/8)
  - Keypoint logit maps (B, 65, H/8, W/8)
  - Reliability/heatmap (B, 1, H/8, W/8)

### Capabilities
- **Keypoint detection:** Identify salient points in images
- **Descriptor generation:** Extract 64-dimensional feature vectors per keypoint
- **Image matching:** Find correspondences between image pairs
- **Loop closure detection:** Recognize revisited locations
- **Visual localization:** Determine camera pose relative to reference frames
- **Dense matching:** Per-pixel descriptor fields for robust matching

### Key Implementation
```python
class XFeatModel(nn.Module):
    """
    Implementation of XFeat: Accelerated Features for Lightweight Image Matching
    https://www.verlab.dcc.ufmg.br/descriptors/xfeat_cvpr24/
    """
    def forward(self, x):
        # Returns:
        # - feats: Dense local features (B, 64, H/8, W/8)
        # - keypoints: Keypoint logit map (B, 65, H/8, W/8)
        # - heatmap: Reliability map (B, 1, H/8, W/8)
```

### Features
- Lightweight and efficient for edge deployment
- Grayscale and RGB image support
- Dense feature extraction (not just sparse keypoints)
- Reliability-weighted matching
- Suitable for Hailo acceleration

### Example Use Cases
- **Autonomous navigation:** Path recording and retracing (Navigator project)
- **SLAM systems:** Visual odometry with loop closure
- **Image stitching/mosaicing:** Wide-baseline image alignment
- **Structure-from-motion:** 3D reconstruction from image sequences
- **Visual place recognition:** Scene retrieval and localization

---

## 5. Traditional ImageNet Classification (Reference)

### Overview
Standard CNN-based image classification models trained on ImageNet (1000 categories). Provided for reference—represents the "short-list" detection you wanted to move beyond.

### Location
- **C++ Application:** `hailo-apps/hailo_apps/cpp/classification/`
- **Models:** Pre-compiled HEF files for Hailo-8/8L/10H
- **Reference Labels:** `hailo-apps/hailo_apps/cpp/classification/imagenet_labels.hpp`

### Supported Models
- **ResNet v1:** resnet_v1_50, resnet_v1_34, resnet_v1_18
- **HardNet:** hardnet68, hardnet39ds
- **FastVIT:** fastvit_sa12

### Architecture
- **Input:** 224×224 RGB images (typically)
- **Output:** 1000-class probability distribution
- **Inference:** Single-label classification

### Capabilities
- Fixed-vocabulary classification (1000 ImageNet categories)
- Fast inference on Hailo hardware
- Well-established benchmarks
- Suitable as feature extractor (intermediate layers)

### Label Examples
From `imagenet_labels.hpp`:
- "tench, Tinca tinca"
- "goldfish, Carassius auratus"
- "great white shark, white shark, man-eater, man-eating shark, Carcharodon carcharias"
- "person"
- "car"
- ... (1000 total categories)

### Key Files
- [classifier.cpp](../hailo-apps/hailo_apps/cpp/classification/classifier.cpp) - Main application
- [imagenet_labels.hpp](../hailo-apps/hailo_apps/cpp/classification/imagenet_labels.hpp) - Label definitions
- [README.md](../hailo-apps/hailo_apps/cpp/classification/README.md) - Usage guide

### Limitations
- **Fixed vocabulary:** Cannot classify outside predefined 1000 classes
- **Single label:** Only returns top-1 (or top-k) prediction
- **No description:** Returns only class name, no detailed attributes

---

## Comparative Analysis

### Vocabulary Richness
| Model | Vocabulary Type | Scale |
|-------|---|---|
| **Florence-2** | Language model (generative) | Unlimited—free-form English text |
| **CLIP** | Open-vocabulary embedding space | Unlimited—arbitrary text descriptions |
| **Qwen VLM** | Language model (generative) | Unlimited—free-form multi-modal reasoning |
| **XFeat** | Dense feature descriptors | 64-dimensional vectors (dense spatial) |
| **ImageNet** | Fixed taxonomy | 1,000 predefined categories |

### Output Modality
| Model | Output Type | Detail Level |
|-------|---|---|
| **Florence-2** | Free-form text caption | Narrative descriptions with arbitrary detail |
| **CLIP** | Similarity scores + top match | Semantic relevance of image to text |
| **Qwen VLM** | Free-form text (generative) | Arbitrary reasoning and multi-turn dialog |
| **XFeat** | Feature vectors + keypoints | Pixel-level correspondence potential |
| **ImageNet** | Class names + scores | Single or top-k predictions |

### Use Case Suitability
| Use Case | Best Model | Rationale |
|----------|---|---|
| Scene description | Florence-2 or Qwen VLM | Generative narrative output |
| Custom visual search | CLIP | Open vocabulary, runtime configurability |
| Image understanding Q&A | Qwen VLM | Multi-modal reasoning capability |
| Visual navigation | XFeat | Dense matching and localization |
| Traditional classification | ImageNet | Speed and established benchmarks |
| Semantic categorization | CLIP or Qwen VLM | Rich descriptive vocabulary |

---

## Integration & Runtime Requirements

### Hardware
- **Hailo-10H:** Primary accelerator for most models
- **Hailo-8/8L:** Limited support (ImageNet classification, detection-based pipelines only)
- **Raspberry Pi 5:** Supported platform for all listed models

### Software Stack
- **HailoRT:** 5.1.1+ (Venice) or 5.2.0+ (Cordoba)
- **TAPPAS Core:** 5.1.0 or 5.2.0 (for GStreamer pipelines)
- **GenAI Model Zoo:** 5.1.1 or 5.2.0 (for VLMs)
- **Python:** 3.10+
- **Dependencies:** OpenCV, PyTorch (for some features), NumPy

### Model Files
- **HEF Format:** Hailo Executable File (optimized for hardware)
- **ONNX Format:** Some vision encoders (not Hailo-accelerated)
- **JSON Configs:** Embeddings and prompt configurations
- **Tokenizer Files:** BPE and SentencePiece formats

---

## Application Examples

### 1. Retail Inventory Monitoring
```
Use CLIP for runtime-configurable searches:
- "empty shelf"
- "stocked shelf"
- "product on wrong shelf"
- "inventory not organized"
```

### 2. Smart Surveillance
```
Combine YOLOv8 detection + Florence-2 captioning:
- Detect persons → Extract crops
- Caption each person
- Alert on unusual descriptions
```

### 3. Autonomous Robot Navigation
```
Use XFeat for path recording/retracing:
- Record path with dense feature descriptors
- Retrace path by matching current frames to recorded keypoints
- No GPS or maps required
```

### 4. Accessibility & Content Description
```
Use Qwen VLM or Florence-2:
- Auto-describe images for visually impaired users
- Generate alt-text for web content
- Real-time scene understanding for navigation
```

### 5. Interactive Visual Search
```
Use CLIP with GUI:
- User enters arbitrary text descriptions
- System highlights matching image regions
- Runtime customization without model retraining
```

---

## Performance Characteristics

### Inference Speed (Approximate, Raspberry Pi 5 + Hailo-10H)
| Model | Throughput | Latency |
|-------|---|---|
| **Florence-2 (full)** | ~1-2 fps | 500-1000ms per image |
| **CLIP encoder** | ~20-30 fps | 33-50ms per image |
| **Qwen2-VL-2B** | ~2-5 fps | 200-500ms per image |
| **XFeat** | ~10-20 fps | 50-100ms per image |
| **ImageNet** | ~30-60 fps | 17-33ms per image |

*Note: Actual performance depends on image resolution, batch size, and model configuration.*

### Memory Requirements
| Model | Approximate VRAM | Notes |
|-------|---|---|
| **Florence-2** | 2-3 GB | Encoder + decoder on device |
| **CLIP** | 1-2 GB | Image encoder on Hailo, text on CPU |
| **Qwen2-VL-2B** | 2-4 GB | Full model on Hailo device |
| **XFeat** | 200-500 MB | Lightweight feature extractor |
| **ImageNet** | 200-500 MB | Standard CNN |

---

## Limitations & Considerations

### Florence-2 (Captioning)
- ✅ Rich narrative descriptions
- ❌ Slower inference (~1-2 fps)
- ❌ No query-specific filtering (generates full caption each time)
- ❌ Sensitive to caption embedding configuration

### CLIP (Zero-Shot)
- ✅ Fast inference, good for real-time
- ✅ Runtime-configurable prompts
- ❌ Requires pre-computed text embeddings
- ❌ Sensitive to prompt phrasing

### Qwen VLM
- ✅ Most flexible (multi-modal reasoning)
- ✅ Supports multi-turn dialog
- ❌ Slower than CLIP
- ❌ Requires larger model weights
- ❌ Context length limited

### XFeat
- ✅ Dense matching enables wide-baseline registration
- ✅ Lightweight and fast
- ❌ Keypoint matching can be ambiguous in textureless regions
- ❌ Requires post-processing for robust matching

### ImageNet
- ✅ Well-optimized and fast
- ❌ Limited to 1000 categories
- ❌ Single-label output
- ❌ No descriptive richness

---

## Recommendations

### For Scene Understanding & Rich Descriptions
**→ Use Florence-2 or Qwen VLM**
- Arbitrary vocabulary
- Narrative-quality output
- Supports multi-modal reasoning

### For Real-Time Query-Based Classification
**→ Use CLIP**
- Fast inference
- Runtime-configurable prompts
- Lower latency than generative models

### For Visual Navigation & Localization
**→ Use XFeat**
- Dense feature matching
- Efficient for path recording/retracing
- Suitable for autonomous systems

### For Interactive Visual Exploration
**→ Use CLIP with GUI**
- User-driven search
- Runtime prompt modification
- Semantic matching without retraining

### For Accessibility
**→ Use Florence-2 or Qwen VLM**
- Natural language descriptions
- General-purpose scene understanding
- Multi-modal capabilities

---

## References

### Models & Papers
- **Florence-2:** Microsoft Research (Image Understanding Foundation Model)
- **CLIP:** [Learning Transferable Visual Models From Natural Language Supervision](https://arxiv.org/abs/2103.00020) — OpenAI
- **Qwen2-VL:** [Qwen2-VL: Enhancing Vision Language Model's Ocr Numbers Reasoning](https://arxiv.org/abs/2409.12191) — Alibaba DAMO
- **XFeat:** [XFeat: Accelerated Features for Lightweight Image Matching](https://www.verlab.dcc.ufmg.br/descriptors/xfeat_cvpr24/) — CVPR 2024

### Repository Links
- **Hailo Apps:** https://github.com/hailo-ai/hailo-apps
- **Hailo Model Zoo GenAI:** https://github.com/hailo-ai/hailo_model_zoo_genai
- **HailoRT:** https://github.com/hailo-ai/hailort
- **Hailo RPi5 Examples:** https://github.com/hailo-ai/hailo-rpi5-examples

### Documentation
- [CLIP Pipeline App README](../hailo-apps/hailo_apps/python/pipeline_apps/clip/README.md)
- [VLM Chat Application](../hailo-apps/hailo_apps/python/gen_ai_apps/vlm_chat/)
- [Florence-2 Dynamic Captioning](../hailo-rpi5-examples/community_projects/dynamic_captioning/)
- [Navigator XFeat Application](../hailo-rpi5-examples/community_projects/Navigator/)
- [Classification C++ Example](../hailo-apps/hailo_apps/cpp/classification/)

---

## Version & Compatibility

**Document Version:** 1.0  
**Date Created:** January 31, 2026  
**HailoRT Compatibility:** 5.1.1 – 5.2.0  
**Hailo Devices:** Hailo-8, Hailo-8L, Hailo-10H  
**Platforms:** Raspberry Pi 5, x86_64 Linux

---

*This document provides a comprehensive overview of vision classification capabilities in the Hailo ecosystem. For the most up-to-date model information, consult the official [Hailo Developer Zone](https://hailo.ai/developer-zone/) and GitHub repositories.*
