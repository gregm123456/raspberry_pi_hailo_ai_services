# Image Classifier Service Recommendations

**Date:** January 31, 2026  
**Context:** Evaluating vision models for deployment as a system service alongside hailo-ollama  
**Requirements:**
- REST endpoint accepting image submissions
- Rich classification capabilities
- Prompt/structured input support for flexible classification
- Preference for existing API conventions
- Suitable for Raspberry Pi 5 + Hailo-10H deployment

---

## Executive Summary

After evaluating all available vision models in the Hailo ecosystem, **Qwen VLM (Qwen2-VL-2B-Instruct)** is the strongest candidate for a prompt-driven image classification service. It offers chat-based API patterns (compatible with Ollama conventions), arbitrary text prompts, structured input support, and rich descriptive responses—making it an ideal complement to the existing hailo-ollama service.

**Recommended Service Name:** `hailo-vision`

---

## Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Prompt Support** | High | Ability to accept text prompts/queries alongside images |
| **API Standards** | High | Adoption of existing API conventions (e.g., OpenAI, Ollama) |
| **Output Richness** | High | Descriptive responses vs. simple class labels |
| **Structured Input** | Medium | Support for JSON/structured query formats |
| **Performance** | Medium | Inference speed and resource efficiency |
| **Implementation** | Medium | Availability of working examples and integrations |

---

## Ranking & Analysis

### 🥇 **1. Qwen VLM (Qwen2-VL-2B-Instruct)**

**Overall Score: 10/10**

#### Strengths

✅ **Conversational API Pattern**
- Uses chat-based message format (role/content pairs)
- Natural fit with Ollama-compatible patterns (proven in hailo-ollama)
- Supports multi-turn dialog for follow-up queries

✅ **Prompt-Driven Classification**
- Accepts arbitrary text prompts alongside images
- Flexible queries: "Is there a person? Describe their clothing."
- Can handle structured questions and open-ended descriptions

✅ **Structured Input/Output**
- JSON message format with typed content blocks
- Configurable generation parameters (temperature, max_tokens)
- Streaming response support

✅ **Rich Descriptive Output**
- Generates natural language responses
- Not limited to predefined categories
- Can provide reasoning and detailed analysis

✅ **Multi-Modal Reasoning**
- Combines image understanding with text generation
- Context-aware responses
- Suitable for complex visual question-answering

#### API Example

```json
POST /v1/chat/completions
Content-Type: application/json

{
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image",
          "image_url": "data:image/jpeg;base64,/9j/4AAQ..."
        },
        {
          "type": "text",
          "text": "Is there a person in this image? If so, describe their clothing and what they're doing."
        }
      ]
    }
  ],
  "temperature": 0.7,
  "max_tokens": 200,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1706745600,
  "model": "qwen2-vl-2b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Yes, there is a person in the image. They are wearing a red shirt and blue jeans. The person appears to be standing in front of a brick building and seems to be looking at their phone."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 256,
    "completion_tokens": 42,
    "total_tokens": 298
  }
}
```

#### Implementation Details

**Location:** `hailo-apps/hailo_apps/python/gen_ai_apps/vlm_chat/`

**Key Files:**
- [vlm_chat.py](../hailo-apps/hailo_apps/python/gen_ai_apps/vlm_chat/vlm_chat.py) - Interactive chat application
- [simple_vlm_chat.py](../hailo-apps/hailo_apps/python/gen_ai_apps/simple_vlm_chat/simple_vlm_chat.py) - Minimal example
- C++ API: `hailort/hailort/libhailort/include/hailo/genai/vlm/vlm.hpp`

**Model Variants:**
- Qwen2-VL-2B-Instruct (recommended: 2-4 GB VRAM)
- Qwen2-VL-7B-Instruct (larger, more capable)
- Qwen3-VL-2B (latest generation)

**Python Bindings:** Available in HailoRT 5.2.0+

#### Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | ~2-5 fps |
| **Latency** | 200-500ms per query |
| **VRAM** | 2-4 GB (2B model) |
| **Concurrent Services** | Compatible with hailo-ollama |
| **Thermal Impact** | Moderate |

#### Service Design Implications

**API Compatibility:**
- Can implement OpenAI Vision API compatibility layer
- Reuses Ollama-compatible patterns from hailo-ollama service
- Consistent developer experience across services

**Context Management:**
- Supports conversation history tracking
- Token limit management (similar to LLM services)
- Stateful vs. stateless endpoint options

**Resource Sharing:**
- Hailo-10H supports concurrent VLM + LLM operation
- Memory budget: ~2-4 GB for vision, ~2-4 GB for text LLM
- Total: 4-8 GB (within Pi 5 constraints)

**Deployment Patterns:**
- systemd service with Type=notify
- Health check endpoints
- Graceful model loading/unloading
- journald logging integration

#### Use Cases

1. **Interactive Visual Question-Answering**
   - "What color is the car in this image?"
   - "How many people are in this photo?"
   - "Is this a safe work environment?"

2. **Accessibility & Alt-Text Generation**
   - Generate detailed image descriptions for visually impaired users
   - Context-aware descriptions based on user needs

3. **Smart Surveillance**
   - "Describe any unusual activity in this frame"
   - "Is anyone wearing safety equipment?"

4. **Content Moderation**
   - "Does this image contain inappropriate content?"
   - "Classify this image as safe/unsafe with reasoning"

5. **Retail & Inventory**
   - "Is this shelf fully stocked?"
   - "What products are visible in this image?"

#### Recommendation

**Best choice for general-purpose image classification service.**

Qwen VLM provides the most flexible, powerful, and developer-friendly approach. Its chat-based API aligns with existing hailo-ollama patterns, making it a natural extension of the service portfolio.

---

### 🥈 **2. CLIP (Zero-Shot Classification)**

**Overall Score: 9/10**

#### Strengths

✅ **Runtime-Configurable Prompts**
- Accepts arbitrary text descriptions for classification
- No retraining required for new categories
- Open vocabulary (not limited to predefined classes)

✅ **Fast Inference**
- ~20-30 fps throughput
- 33-50ms latency per image
- Suitable for real-time applications

✅ **Ensemble Support**
- Multiple prompt template variations for robustness
- "a photo of a {text}"
- "a photo of the {text}"
- "a photo of my {text}"

✅ **Proven Architecture**
- CLIP is widely adopted in industry
- Well-documented model and API patterns
- Strong community support

✅ **Lightweight Resource Profile**
- 1-2 GB VRAM
- Low thermal impact
- Good for concurrent operation

#### Weaknesses

⚠️ **No Standard REST API**
- Would need custom API design
- No existing convention like Ollama or OpenAI

⚠️ **Limited Output Format**
- Returns similarity scores, not descriptive text
- Top-k matching rather than generative responses

#### Proposed API Design

```json
POST /v1/classify
Content-Type: application/json

{
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "prompts": [
    "person wearing red shirt",
    "person wearing blue shirt",
    "person wearing jacket",
    "person carrying backpack"
  ],
  "threshold": 0.5,
  "top_k": 3,
  "ensemble": true
}
```

**Response:**
```json
{
  "classifications": [
    {
      "text": "person wearing red shirt",
      "score": 0.87,
      "rank": 1
    },
    {
      "text": "person wearing jacket",
      "score": 0.62,
      "rank": 2
    },
    {
      "text": "person carrying backpack",
      "score": 0.54,
      "rank": 3
    }
  ],
  "inference_time_ms": 35,
  "model": "clip-resnet-50x4"
}
```

#### Implementation Details

**Location:** `hailo-apps/hailo_apps/python/pipeline_apps/clip/`

**Key Files:**
- [clip.py](../hailo-apps/hailo_apps/python/pipeline_apps/clip/clip.py) - Core pipeline
- [text_image_matcher.py](../hailo-apps/hailo_apps/python/pipeline_apps/clip/text_image_matcher.py) - Text embedding generation
- [README.md](../hailo-apps/hailo_apps/python/pipeline_apps/clip/README.md) - Comprehensive usage guide
- C++ implementation: `hailo-apps/hailo_apps/cpp/zero_shot_classification/`

**Models:**
- CLIP ResNet-50x4 (640-dimensional embeddings)
- Hailo-optimized HEF files available

**Features:**
- GTK GUI for interactive testing
- Embedding persistence (JSON format)
- Batch processing support
- Multiple detection modes (full frame, person crops, face crops)

#### Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | ~20-30 fps |
| **Latency** | 33-50ms per image |
| **VRAM** | 1-2 GB |
| **Concurrent Services** | Excellent compatibility |
| **Thermal Impact** | Low |

#### Service Design Implications

**API Design Needed:**
- No existing standard to adopt
- Opportunity to define clean, idiomatic REST API
- Could support both single-image and batch endpoints

**Text Embedding Strategy:**
- Pre-compute embeddings for frequent prompts
- On-the-fly generation for ad-hoc queries
- Caching layer for performance

**Integration Patterns:**
- Can combine with object detection (YOLOv8 → CLIP on crops)
- Pipeline mode: detect → classify → annotate
- Suitable for real-time video streams

#### Use Cases

1. **Real-Time Visual Search**
   - Match video frames against custom search terms
   - Runtime-configurable without model retraining

2. **Retail Monitoring**
   - "empty shelf" vs. "stocked shelf"
   - "product on wrong shelf"
   - "inventory not organized"

3. **Security & Access Control**
   - Person attribute classification
   - "person wearing uniform"
   - "person carrying prohibited item"

4. **Smart Home Automation**
   - Scene understanding triggers
   - "person cooking" → turn on ventilation
   - "person reading" → adjust lighting

#### Recommendation

**Choose CLIP if:**
- Real-time performance is critical (10-20x faster than VLM)
- Classification needs are simpler (matching to descriptors)
- Running many concurrent services with limited resources
- Need very low latency (<50ms)

**Trade-off:**
- Less conversational capability than VLM
- No generative/descriptive output
- Requires custom API design

---

### 🥉 **3. Florence-2 (Image Captioning)**

**Overall Score: 7/10**

#### Strengths

✅ **Rich Narrative Descriptions**
- Generates high-quality, natural language captions
- Describes scenes, objects, spatial relationships, context

✅ **Arbitrary Vocabulary**
- Not constrained by predefined classes
- Language model generative capability

✅ **Existing Implementation**
- Full pipeline available in hailo-rpi5-examples
- Scene change detection included
- Text-to-speech integration example

#### Weaknesses

❌ **No Prompt Support**
- Generates full captions without specific queries
- Cannot answer targeted classification questions directly
- One-size-fits-all output

❌ **Slower Inference**
- ~1-2 fps throughput
- 500-1000ms latency per image
- Not suitable for real-time applications

❌ **No Standard API**
- Would need custom REST design
- No existing conventions to adopt

❌ **Resource Intensive**
- 2-3 GB VRAM (encoder + decoder)
- Higher thermal impact

#### Proposed API Design

```json
POST /v1/caption
Content-Type: application/json

{
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "max_length": 100,
  "min_length": 10
}
```

**Response:**
```json
{
  "caption": "A person wearing a red shirt and blue jeans standing in front of a brick building while looking at their phone",
  "inference_time_ms": 750,
  "model": "florence-2"
}
```

#### Implementation Details

**Location:** `hailo-rpi5-examples/community_projects/dynamic_captioning/`

**Key Files:**
- [caption.py](../hailo-rpi5-examples/community_projects/dynamic_captioning/caption.py) - Full inference pipeline
- [README.md](../hailo-rpi5-examples/community_projects/dynamic_captioning/README.md) - Installation guide

**Architecture:**
- **Vision Encoder:** DaViT (Dual Attention ViT) - ONNX runtime
- **Text Encoder:** Hailo-accelerated
- **Decoder:** Hailo-accelerated transformer
- **Tokenizer:** HuggingFace tokenizer

**Features:**
- Scene change detection via CLIP embeddings
- Text-to-speech output (espeak)
- Async encoder-decoder processing

#### Performance Characteristics

| Metric | Value |
|--------|-------|
| **Throughput** | ~1-2 fps |
| **Latency** | 500-1000ms per image |
| **VRAM** | 2-3 GB |
| **Concurrent Services** | Moderate compatibility |
| **Thermal Impact** | Moderate-High |

#### Use Cases

1. **Accessibility Alt-Text**
   - Automatic image descriptions for screen readers
   - General-purpose scene understanding

2. **Video Annotation**
   - Automated metadata generation
   - Scene description archival

3. **Content Cataloging**
   - Describe images in photo libraries
   - Generate searchable text from visual content

#### Recommendation

**Choose Florence-2 if:**
- Need general-purpose scene descriptions
- Building accessibility features (alt-text, audio descriptions)
- Batch processing acceptable (not real-time)
- Don't need query-specific classification

**Limitations:**
- Not suitable for targeted classification queries
- Would need NLP post-processing to extract specific attributes
- Slower than alternatives

---

### 4. **ImageNet Traditional Classifiers**

**Overall Score: 3/10**

#### Strengths

✅ **Very Fast**
- 30-60 fps throughput
- 17-33ms latency
- Minimal resource overhead

✅ **Lightweight**
- 200-500 MB VRAM
- Low thermal impact
- Excellent for concurrent operation

✅ **Well-Optimized**
- Multiple model variants (ResNet, HardNet, FastVIT)
- Established benchmarks
- Proven deployment patterns

#### Weaknesses

❌ **Fixed Vocabulary**
- Limited to 1000 predefined ImageNet categories
- Cannot classify outside this taxonomy

❌ **No Prompt Support**
- Single-label classification only
- No structured input flexibility

❌ **Limited Output Richness**
- Returns class names and scores
- No descriptions or attributes

❌ **Poor Match for Requirements**
- Does not meet "rich classification" requirement
- No prompt-driven capability

#### API Example (Hypothetical)

```json
POST /v1/classify/imagenet
Content-Type: application/json

{
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "top_k": 5
}
```

**Response:**
```json
{
  "classifications": [
    {"class": "golden retriever", "score": 0.92, "class_id": 207},
    {"class": "Labrador retriever", "score": 0.05, "class_id": 208},
    {"class": "cocker spaniel, English cocker spaniel", "score": 0.02, "class_id": 219}
  ],
  "inference_time_ms": 18,
  "model": "resnet_v1_50"
}
```

#### Implementation Details

**Location:** `hailo-apps/hailo_apps/cpp/classification/`

**Available Models:**
- ResNet v1: 50, 34, 18
- HardNet: 68, 39ds
- FastVIT: sa12

**Features:**
- C++ implementation
- Pre-compiled HEF files
- 1000 ImageNet class labels

#### Recommendation

**Only choose ImageNet classifiers if:**
- Need extremely fast classification (speed is paramount)
- Classification domain fits within 1000 ImageNet categories
- Building a benchmark or reference implementation

**Not recommended for this use case** due to lack of prompt support and limited vocabulary.

---

### 5. **XFeat (Dense Feature Descriptors)**

**Overall Score: 1/10**

#### Why It's Not Suitable

❌ **Not a Classifier**
- Extracts dense feature descriptors for image matching
- No classification capability

❌ **No Text Interface**
- Works with visual feature matching only
- Cannot accept prompts or queries

❌ **Different Use Case**
- Designed for SLAM, navigation, loop closure
- Image-to-image matching, not image classification

#### What It Does

XFeat extracts 64-dimensional feature vectors at keypoints for:
- Visual localization
- Loop closure detection
- Image stitching/mosaicing
- Structure-from-motion

#### Implementation Details

**Location:** `hailo-rpi5-examples/community_projects/Navigator/`

**Architecture:**
- CNN-based keypoint detector
- Dense descriptor extraction
- Reliability-weighted matching

#### Recommendation

**Do not use XFeat for image classification service.**

It is designed for a completely different purpose (visual navigation and SLAM).

---

## Comparative Summary

| Model | Prompt Support | API Standard | Output Richness | Speed | Resource | Overall |
|-------|----------------|--------------|-----------------|-------|----------|---------|
| **Qwen VLM** | ✅✅✅ | ✅✅ (Ollama-like) | ✅✅✅ | ⚠️ Moderate | ⚠️ Moderate | **10/10** |
| **CLIP** | ✅✅ | ⚠️ Custom needed | ⚠️ Scores only | ✅✅✅ | ✅✅ | **9/10** |
| **Florence-2** | ❌ None | ⚠️ Custom needed | ✅✅ | ❌ Slow | ⚠️ Heavy | **7/10** |
| **ImageNet** | ❌ None | ⚠️ Custom needed | ❌ Labels only | ✅✅✅ | ✅✅✅ | **3/10** |
| **XFeat** | ❌ N/A | ❌ N/A | ❌ N/A | N/A | N/A | **1/10** |

---

## Recommended Path Forward

### Primary Recommendation: **hailo-vision Service (Qwen VLM)**

#### Service Design

**Service Name:** `hailo-vision`

**API Compatibility:** OpenAI Vision API with Ollama-style patterns

**Key Endpoints:**
```
POST /v1/chat/completions         # Primary vision chat interface
GET  /v1/models                   # List available vision models
POST /v1/embeddings               # Image embeddings (future)
GET  /health                      # Service health check
GET  /metrics                     # Prometheus metrics
```

**Configuration Strategy:**
```yaml
# /etc/hailo/vision/config.yaml
model:
  name: qwen2-vl-2b-instruct
  path: /opt/hailo/models/qwen2-vl-2b/
  warmup: true
  persistent: true

inference:
  max_tokens: 512
  temperature: 0.7
  top_p: 0.95
  
resources:
  max_batch_size: 1
  memory_limit_mb: 4096
  
api:
  host: 127.0.0.1
  port: 11435
  cors_enabled: false
```

**systemd Integration:**
```ini
[Unit]
Description=Hailo Vision Classification Service
After=network.target hailo-ollama.service
Requires=hailo.service

[Service]
Type=notify
User=hailo-vision
Group=hailo
EnvironmentFile=/etc/hailo/vision/environment
ExecStart=/opt/hailo/vision/bin/vision-server
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

#### Resource Budget (Concurrent Operation)

Assuming both hailo-ollama (LLM) and hailo-vision (VLM) running:

| Service | VRAM | System RAM | CPU | Hailo NPU |
|---------|------|------------|-----|-----------|
| **hailo-ollama** | 2-4 GB | 1-2 GB | 10-20% | 40-60% |
| **hailo-vision** | 2-4 GB | 1-2 GB | 10-20% | 40-60% |
| **System Overhead** | - | 1-2 GB | 10-20% | - |
| **Total** | 4-8 GB | 4-6 GB | 30-60% | Shared |

**Raspberry Pi 5 Capacity:** ~6 GB usable RAM, shared Hailo-10H NPU

**Verdict:** ✅ Feasible with careful resource management

**Considerations:**
- Both services share Hailo-10H bandwidth
- Load models persistently (avoid startup latency)
- Monitor thermal throttling under sustained load
- Consider sequential loading if memory tight
- Implement graceful degradation if resources constrained

#### Implementation Phases

**Phase 1: Core Service**
- Qwen VLM integration with HailoRT bindings
- Basic REST API (chat completions endpoint)
- Single-image, single-prompt support
- Health check and metrics

**Phase 2: API Compatibility**
- OpenAI Vision API compatibility layer
- Streaming response support
- Multi-turn conversation handling
- Context management

**Phase 3: Optimization**
- Batching support
- Embedding caching
- Resource monitoring
- Thermal management

**Phase 4: Advanced Features**
- Multi-image support
- Video frame sequences
- Custom fine-tuning support (future)

---

### Alternative Recommendation: **hailo-clip Service**

**Choose CLIP if:**
- Real-time performance is critical (>10 fps required)
- Running resource-constrained with many concurrent services
- Classification needs are simpler (matching to text descriptors)
- Want lower thermal impact

**Service Design:**
Similar patterns to hailo-vision but with different endpoints:

```
POST /v1/classify                 # Zero-shot classification
POST /v1/embeddings/image         # Image embeddings
POST /v1/embeddings/text          # Text embeddings
POST /v1/match                    # Batch image-text matching
GET  /health                      # Health check
```

**Trade-offs:**
- 10-20x faster inference
- Lower resource usage
- Less flexible output (scores vs. descriptions)
- Requires custom API design

---

## Next Steps

### Immediate Actions

1. **Review Qwen VLM examples**
   - Run `vlm_chat.py` to test model behavior
   - Verify resource usage with monitoring
   - Test concurrent operation with hailo-ollama

2. **Design REST API specification**
   - Define endpoint contracts
   - Request/response schemas
   - Error handling patterns
   - Authentication/authorization strategy

3. **Plan systemd service architecture**
   - Service unit configuration
   - User/group permissions
   - File system layout
   - Logging strategy

4. **Benchmark resource usage**
   - Memory footprint (VRAM + system RAM)
   - CPU utilization
   - Hailo NPU bandwidth
   - Thermal characteristics
   - Concurrent operation profile

### Documentation Requirements

Following hailo-ollama patterns:

- `system_services/hailo-vision/README.md` — Overview and installation
- `system_services/hailo-vision/API_SPEC.md` — REST API reference
- `system_services/hailo-vision/ARCHITECTURE.md` — Design decisions
- `system_services/hailo-vision/TROUBLESHOOTING.md` — Common issues
- `system_services/hailo-vision/install.sh` — Deployment script
- `system_services/hailo-vision/config.yaml` — Configuration template

---

## Conclusion

**Qwen VLM** is the clear winner for a prompt-driven, rich image classification service. Its chat-based API aligns perfectly with existing hailo-ollama patterns, provides maximum flexibility, and delivers the descriptive, conversational output needed for modern AI applications.

**CLIP** remains an excellent alternative for latency-sensitive or resource-constrained scenarios where speed matters more than output richness.

The path forward is to design and implement **hailo-vision** as a companion service to hailo-ollama, creating a unified AI service ecosystem on the Raspberry Pi 5 + Hailo-10H platform.

---

**Document Version:** 1.0  
**Author:** System Architecture Analysis  
**Status:** Recommendation Complete — Ready for Design Phase  
**Next Document:** `hailo-vision_build_plan.md`
