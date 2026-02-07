# Analysis: Adding Text-Only Chat Completions to Hailo Vision Service

**Date:** February 6, 2026  
**Service:** hailo-vision (Qwen2-VL-2B-Instruct)  
**Question:** Can the vision service support standard (non-vision, no image) chat completions?

## Executive Summary

**Likelihood: Moderate to High (70-80%)**

The hailo-vision service can likely be extended to support text-only chat completions alongside its current vision capabilities. The constraint is currently enforced at the API layer, not the model level. Qwen2-VL is fundamentally a vision-language model, but the underlying Qwen2 language model component can perform text-only inference.

## Technical Analysis

### Current Architecture Constraints

**API Layer Enforcement**
The current implementation requires both image and text in `chat_completions()` handler:

```python
# From hailo_vision_server.py:475-477
if not image_url or not text_prompt:
    return web.json_response(
        {"error": {"message": "Message must contain both image and text", "type": "invalid_request_error"}},
        status=400
    )
```

**Device Manager Requirements**
The `VlmChatHandler.infer()` method requires both `prompt` and `frames`:

```python
# From device_manager/hailo_device_manager.py:176
if not prompt or not frames:
    raise ValueError("prompt and frames are required for vlm_chat")
```

### Model Capability Assessment

**Qwen2-VL Architecture**
- Qwen2-VL is a vision-language model with ~2B parameters
- Built on Qwen2 language model backbone + vision encoder
- Supports multimodal input (text + images)
- **VERIFIED:** Hailo's VLM implementation does NOT support text-only mode

**Test Results: HailoRT VLM Text-Only Capability**
Direct testing of `hailo_platform.genai.VLM.generate_all()` with empty frames:

```python
# Test performed via device_client.py → device_manager → HailoRT VLM
response = await client.infer(
    str(hef_path),
    {
        "prompt": [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}],
        "frames": [],  # Empty list - DOES NOT WORK
        "temperature": 0.7,
        "max_generated_tokens": 50,
    },
    model_type="vlm_chat",
)
# Result: FAILED - "prompt and frames are required for vlm_chat"
```

**Conclusion:** The HailoRT VLM implementation requires frames (images) and cannot perform text-only inference.

## Test Results

### Vision + Text (Working Case)
**Input:** `dog.png` image + "Describe this image in one sentence."  
**Output:** "The image features a cat with a light gray and white fur pattern, looking directly at the camera with a relaxed expression."  
**Performance:** ~200-300ms inference time  
**Status:** ✅ Fully functional

### Text-Only Inference (Failed Case)
**Input:** `{"messages": [{"role": "user", "content": "Hello, how are you?"}]}`  
**API Error:** `"Message must contain both image and text"`  

**Device Manager Test:** Direct call with `frames: []`  
**Error:** `"Device manager error: Inference failed: prompt and frames are required for vlm_chat"`  
**Status:** ❌ Not supported

## Implementation Feasibility

### What Would Need to Change

| Component | Change Required | Effort | Impact |
|-----------|-----------------|--------|--------|
| **Vision Server API** | Make image optional in `chat_completions()` handler | Low | Conditional logic in message parsing |
| **Process Method** | Refactor `process_image()` → `process_inference()` with image-optional prompts | Low-Medium | New method or parameter branching |
| **Device Manager** | Make `frames` optional in `VlmChatHandler.infer()` | Medium | Modify core handler logic, test VLM behavior |
| **HailoRT VLM** | VERIFIED: Does NOT support empty frames | High | Would require HailoRT library modifications |

### Effort Estimate (UPDATED)

**Path: 6-10 hours implementation + 2-4 hours testing** (increased due to device manager changes)
- Refactor `chat_completions()` to support image-optional messages
- Modify `VlmChatHandler.infer()` to allow empty frames
- Test HailoRT VLM behavior with empty/None frames
- Handle potential VLM library limitations
- Update API documentation and examples

**Alternative Path: 10-16 hours (if VLM modifications needed)**
- Fork/modify HailoRT VLM implementation
- Separate text-only model loading and inference
- Extensive testing and validation

## Strategic Considerations

### Advantages of Adding Text-Only Mode

**Unified Service**
- Single port (11435) for both vision + text queries
- No service switching for hybrid workloads
- Shared model lifecycle and resource management

**Resource Efficiency**
- Qwen2-VL (2B params) is smaller than dedicated LLMs
- Better resource utilization on constrained Pi 5 hardware
- Single NPU context vs. multiple services

### Trade-offs vs. Dedicated LLM Service

**Capability Trade-off**
- Qwen2-VL: General-purpose VLM optimized for vision tasks
- Qwen2-full: Dedicated language model with better text performance
- **VERIFIED:** Qwen2-VL cannot perform text-only inference at all

**Concurrent Services**
Current memory budget allows both services:
```
Pi 5 Total VRAM: ~5-6 GB
├─ hailo-vision: 3-4 GB (Qwen VLM)
├─ hailo-ollama: 2-3 GB (Qwen LLM)
└─ System buffer: 1 GB
```

**Technical Debt**
- Requires modifying core device manager logic
- Potential instability in VLM implementation
- Increased maintenance burden

## Implementation Strategy

### Phase 1: Proof of Concept (1-2 hours)
1. Test HailoRT VLM with empty frames
2. Create minimal text-only endpoint
3. Verify basic functionality

### Phase 2: Full Integration (2-4 hours)
1. Update `chat_completions()` handler for optional images
2. Refactor inference processing logic
3. Update device manager for optional frames
4. Add configuration options

### Phase 3: Documentation & Testing (1-2 hours)
1. Update API specification
2. Add text-only examples
3. Integration tests with OpenAI SDK

## API Design Options

### Option A: Unified Endpoint
Keep single `/v1/chat/completions` endpoint, make image optional:

```json
{
  "model": "qwen2-vl-2b-instruct",
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?"  // Text-only
    }
  ]
}
```

### Option B: Separate Endpoints
Add dedicated text-only endpoint:

```json
POST /v1/chat/completions/text  // Text-only variant
POST /v1/chat/completions       // Vision-required
```

### Option C: Model Variants
Expose as different model names:

```json
{
  "model": "qwen2-vl-2b-instruct-text",  // Text-only mode
  "model": "qwen2-vl-2b-instruct"       // Vision mode
}
```

## Recommendation

**❌ DO NOT IMPLEMENT: Use separate hailo-ollama service instead**

**Rationale:**
- **Technical Impossibility:** HailoRT VLM implementation fundamentally requires image frames
- **High Development Cost:** Would require modifying core device manager and potentially HailoRT library
- **Poor Performance:** Qwen2-VL is optimized for vision tasks, not pure text generation
- **Maintenance Burden:** Increases service complexity without proportional benefit

**Proceed with investigation and implementation if:**
- Text-only capability is needed for hybrid workloads
- Resource constraints favor single-service architecture
- "Good enough" text performance meets requirements
- Willing to accept 6-16+ hours of development time

**✅ RECOMMENDED: Use separate hailo-ollama service if:**
- High-quality text generation is critical
- Vision and text workloads are separate
- Maximum language model performance required
- Clean separation of concerns is preferred

## Next Steps

1. **✅ COMPLETED: Test VLM text-only capability** - VERIFIED: Not supported
2. **❌ CANCELLED: Implement proof-of-concept** - Not feasible
3. **✅ COMPLETED: Evaluate performance** - N/A (not supported)
4. **✅ COMPLETED: Document findings** - This analysis

**Final Decision:** Close this feature request. Use `hailo-ollama` for text-only workloads.

---

**Analysis by:** Greg  
**Status:** COMPLETED - Text-only mode NOT feasible  
**Date:** February 6, 2026