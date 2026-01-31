# Hailo Vision Service - Model Manifest Discovery

This document describes the vision models available in the hailo-vision service via Qwen VLM.

## Qwen2-VL-2B-Instruct

**Model Name:** `qwen2-vl-2b-instruct`

**Description:** 
Large vision-language model (2 billion parameters) optimized for visual question-answering and image analysis. Processes images alongside text prompts to generate descriptive responses.

### Capabilities

- **Visual Understanding:** Object detection, scene description, spatial reasoning
- **Text Generation:** Natural language responses to visual queries
- **Conversational:** Multi-turn dialog with image context
- **Flexible Prompts:** Arbitrary text questions (not limited to predefined classes)

### Model Details

| Property | Value |
|----------|-------|
| Model Family | Qwen2-VL |
| Parameter Count | 2 billion (2B) |
| Instruction Tuned | Yes |
| Quantization | int8 (default) |
| Vision Encoder | ViT-based |
| Language Model | Qwen2 LLM |
| Max Context Length | 8192 tokens |
| Max Image Resolution | 8 MP (3840×2160) |

### Use Cases

1. **Image Captioning & Description**
   - Automatic alt-text generation
   - Scene understanding and annotation

2. **Visual Question Answering (VQA)**
   - "Is there a person in this image?"
   - "What color is the car?"
   - "Describe the clothing of people visible"

3. **Content Moderation**
   - "Is this image safe for work?"
   - "Does this contain prohibited items?"

4. **Accessibility**
   - Context-aware image descriptions for blind/low-vision users
   - Emotional or action-based descriptions

5. **Retail & Inventory**
   - "Is this shelf fully stocked?"
   - "What products are visible?"
   - "Are price tags visible?"

6. **Safety & Compliance**
   - "Is anyone wearing safety equipment?"
   - "Are emergency exits visible?"
   - "Describe any hazards visible"

### API Examples

**Basic Image Description:**
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "image", "image_url": {"url": "data:image/jpeg;base64,..."}},
          {"type": "text", "text": "Describe this image in detail."}
        ]
      }
    ],
    "temperature": 0.7,
    "max_tokens": 200,
    "stream": false
  }'
```

**Safety Classification:**
```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2-vl-2b-instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "image", "image_url": {"url": "data:image/jpeg;base64,..."}},
          {"type": "text", "text": "Is this image safe for work? Answer SAFE or UNSAFE."}
        ]
      }
    ],
    "temperature": 0.0,
    "max_tokens": 10
  }'
```

### Performance Characteristics

| Metric | Value |
|--------|-------|
| Average Latency | 200–600 ms |
| Peak Throughput | 2–5 images/sec |
| Memory Load | 2–4 GB VRAM |
| Thermal Profile | Moderate |
| Device Support | Hailo-10H NPU |

### Configuration Parameters

**Server:**
- `host` - Bind address (default: `0.0.0.0`)
- `port` - Listen port (default: `11435`)

**Model:**
- `name` - Model identifier (default: `qwen2-vl-2b-instruct`)
- `keep_alive` - Model lifecycle (default: `-1` = persistent)
  - `-1` = Keep loaded indefinitely
  - `0` = Unload immediately after request
  - `N` = Unload after N seconds

**Generation:**
- `temperature` - Randomness (0.0–2.0; default: `0.7`)
- `max_tokens` - Max output length (default: `200`)
- `top_p` - Nucleus sampling (0.0–1.0; default: `0.9`)
- `seed` - Reproducibility (default: `null` = random)

### Resource Management

**Concurrent Services:**
This service can run alongside `hailo-ollama` or other AI services:

```
Pi 5 Total VRAM: ~5-6 GB
├─ hailo-vision: 3-4 GB (Qwen VLM)
├─ hailo-ollama: 2-3 GB (Qwen LLM)
└─ System buffer: 1 GB
```

Monitor memory:
```bash
free -h
ps aux | grep hailo
```

### Troubleshooting

**Service not responding:**
```bash
sudo systemctl status hailo-vision.service
sudo journalctl -u hailo-vision.service -f
```

**Image too large:**
- Max: 8 MP (typically 3840×2160 or smaller)
- Resize before sending if needed

**Out of memory:**
- Reduce `max_tokens` in config
- Or close other services to free VRAM

### Future Model Variants

Potential extensions (not yet implemented):
- **Qwen2-VL-7B:** Larger, more capable variant
- **Qwen3-VL-2B:** Latest generation (if released)
- **Other VLMs:** Ming-VL, LLaVA, etc. (via integration)

---

## Service API Reference

For full API documentation, see [API_SPEC.md](API_SPEC.md).

**Key Endpoints:**
- `GET /health` - Service status
- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Vision inference
- `POST /v1/vision/analyze` - Batch analysis

---

## Integration Examples

### Python Client
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11435/v1", api_key="dummy")

response = client.chat.completions.create(
    model="qwen2-vl-2b-instruct",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "image", "image_url": {"url": "data:image/jpeg;base64,..."}},
                {"type": "text", "text": "Describe this image."}
            ]
        }
    ],
    temperature=0.7,
    max_tokens=200
)

print(response.choices[0].message.content)
```

### Node.js / JavaScript
```javascript
const response = await fetch('http://localhost:11435/v1/chat/completions', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    model: 'qwen2-vl-2b-instruct',
    messages: [
      {
        role: 'user',
        content: [
          {type: 'image', image_url: {url: 'data:image/jpeg;base64,...'}},
          {type: 'text', text: 'Describe this image.'}
        ]
      }
    ],
    temperature: 0.7,
    max_tokens: 200
  })
});

const result = await response.json();
console.log(result.choices[0].message.content);
```

### cURL
See [API_SPEC.md](API_SPEC.md) for comprehensive cURL examples.
