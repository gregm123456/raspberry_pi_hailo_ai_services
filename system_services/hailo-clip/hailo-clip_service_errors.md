# Hailo-CLIP Service Import Error - Progress Report

**Date:** January 31, 2026  
**Status:** Service running but using mock model fallback

---

## Problem Summary

The `hailo-clip` systemd service starts successfully and responds to HTTP requests, but **fails to import the CLIP model from the hailo-apps submodule**, resulting in the service falling back to a mock implementation that returns random embeddings instead of performing actual AI inference.

### Error Message

```
ModuleNotFoundError: No module named 'hailo_apps.python.pipeline_apps.clip'
```

### Current Behavior

1. Service starts: ✅ (systemd shows `active (running)`)
2. HTTP health endpoint: ✅ (`/health` returns 200)
3. Model loading: ❌ (Falls back to mock with random embeddings)
4. Actual inference: ❌ (Not functional)

---

## Root Cause Analysis

### 1. Package Structure Issue

The `hailo-apps` package is installed as an **editable package** (`pip install -e`):
```bash
Location: /opt/hailo-clip/venv/lib/python3.13/site-packages
Editable project location: /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps
```

**Problem:** Python can import up to `hailo_apps.python.pipeline_apps` but **not** `hailo_apps.python.pipeline_apps.clip`

**Investigation Results:**
```bash
# These succeed:
python3 -c "import hailo_apps.python; print('OK')"  # ✅
python3 -c "import hailo_apps.python.pipeline_apps; print('OK')"  # ✅

# This fails:
python3 -c "import hailo_apps.python.pipeline_apps.clip; print('OK')"  # ❌

# pkgutil shows no submodules:
python3 -c "import pkgutil; import hailo_apps.python.pipeline_apps as p; print([m.name for m in pkgutil.iter_modules(p.__path__)])"
# Returns: []
```

### 2. Missing `__init__.py` Files

The hailo-apps package was missing `__init__.py` files in critical intermediate directories:
- ❌ `/hailo-apps/hailo_apps/__init__.py` (missing)
- ❌ `/hailo-apps/hailo_apps/python/__init__.py` (missing)
- ❌ `/hailo-apps/hailo_apps/python/pipeline_apps/__init__.py` (missing)
- ✅ `/hailo-apps/hailo_apps/python/pipeline_apps/clip/__init__.py` (exists but empty)

**File Listing:**
```bash
$ ls -la /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps/hailo_apps/python/pipeline_apps/
# Shows only subdirectories, NO __init__.py
drwxr-xr-x 13 gregm gregm 4096 Jan 31 08:24 .
drwxr-xr-x  6 gregm gregm 4096 Jan 31 08:24 ..
drwxr-xr-x  4 gregm gregm 4096 Jan 31 20:39 clip/ (contains __init__.py)
drwxr-xr-x  2 gregm gregm 4096 Jan 31 08:24 depth/
drwxr-xr-x  2 gregm gregm 4096 Jan 31 08:24 detection/
...
```

### 3. Missing CLIP Class Implementation

**Critical Discovery:** The `CLIP` class that the service tries to import **does not exist** in the hailo-apps codebase.

**Expected import:**
```python
from hailo_apps.python.pipeline_apps.clip.clip import CLIP
```

**Actual content of `clip.py`:**
```python
# Only contains:
def app_callback(pad, info, user_data): ...
def main(): ...
# NO class CLIP
```

**What exists instead:**
- `GStreamerClipApp` - Full GStreamer pipeline application
- `run_text_encoder_inference()` - Utility for text encoding
- `text_image_matcher` - Singleton for matching text to images
- Various GUI and pipeline utilities

**Architecture mismatch:**
- **Service expects:** Simple class-based API (`model.encode_image()`, `model.encode_text()`)
- **hailo-apps provides:** GStreamer pipeline-based application designed for video streams

---

## Solutions Attempted

### ✅ 1. Virtual Environment with System Site Packages

**Problem:** Missing `gi` (GObject Introspection) module  
**Solution:** Created venv with `--system-site-packages`  
**Result:** Fixed `gi` import but did not resolve main import issue

```bash
# Modified install.sh:
python3 -m venv --system-site-packages "${SERVICE_DIR}/venv"
```

### ✅ 2. Updated requirements.txt

**Problem:** Missing Python dependencies  
**Solution:** Added all dependencies from hailo-apps `pyproject.toml`  
**Result:** All packages installed successfully (scipy, loguru, setproctitle, etc.)

**Current requirements.txt:**
```
PyYAML>=6.0
numpy>=1.24
Pillow>=10.0
torch>=2.0
torchvision>=0.15
opencv-python<=4.10.0.84
Flask>=3.0
requests>=2.31
setproctitle
python-dotenv
loguru
scipy>=1.9.3
tqdm
```

### ❌ 3. PYTHONPATH Environment Variable

**Problem:** Editable install not resolving nested imports  
**Solution:** Added `PYTHONPATH=/home/gregm/raspberry_pi_hailo_ai_services/hailo-apps` to systemd unit  
**Result:** No change, still cannot import `clip` submodule

```ini
# hailo-clip.service
Environment=PYTHONPATH=/home/gregm/raspberry_pi_hailo_ai_services/hailo-apps
```

### ⏸️ 4. Adding __init__.py Files (In Progress)

**Problem:** Python namespace package not recognizing subdirectories  
**Solution:** Create empty `__init__.py` files in intermediate directories  
**Status:** Files created but not yet tested (user cancelled before restart)

```bash
touch /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps/hailo_apps/__init__.py
touch /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps/hailo_apps/python/__init__.py
touch /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps/hailo_apps/python/pipeline_apps/__init__.py
```

### ⏸️ 5. Stub CLIP Class Implementation (In Progress)

**Problem:** No `CLIP` class exists in hailo-apps  
**Solution:** Created minimal stub class in `clip.py`  
**Status:** File written but requires `__init__.py` fix to be importable

**Created stub:**
```python
# /hailo-apps/hailo_apps/python/pipeline_apps/clip/clip.py
class CLIP:
    def __init__(self, model_name="clip-resnet-50x4", device_id=0):
        self.model_name = model_name
        self.device_id = device_id
        
    def encode_image(self, image_array):
        # Image encoding placeholder (returns random for now)
        return np.random.randn(640).astype(np.float32)

    def encode_text(self, text):
        # Text encoding placeholder (returns random for now)
        return np.random.randn(640).astype(np.float32)
```

---

## Current Status

### Service State
```bash
$ sudo systemctl status hailo-clip.service
● hailo-clip.service - Hailo CLIP (Zero-Shot Image Classification on Hailo-10H)
     Loaded: loaded (/etc/systemd/system/hailo-clip.service; enabled)
     Active: active (running)
```

### Log Output
```
Jan 31 20:57:27 pi5ai2 python3[24761]: INFO - Starting Hailo CLIP Service
Jan 31 20:57:27 pi5ai2 python3[24761]: INFO - Loaded config from /etc/hailo/hailo-clip.yaml
Jan 31 20:57:27 pi5ai2 python3[24761]: INFO - CLIPModel initialized: clip-resnet-50x4 on device 0
Jan 31 20:57:27 pi5ai2 python3[24761]: ERROR - Failed to import CLIP from hailo-apps: No module named 'hailo_apps.python.pipeline_apps.clip'
Jan 31 20:57:27 pi5ai2 python3[24761]: INFO - Using fallback mock model for development
Jan 31 20:57:27 pi5ai2 python3[24761]: WARNING - Using mock CLIP model (set HAILO_CLIP_MOCK=false to disable)
Jan 31 20:57:27 pi5ai2 python3[24761]: INFO - Listening on 0.0.0.0:5000
```

### HTTP API
```bash
$ curl http://localhost:5000/health
{
  "status": "healthy",
  "service": "hailo-clip",
  "model_loaded": true,  # Actually using mock
  "model": "clip-resnet-50x4"
}
```

---

## Next Steps

### Option A: Complete Stub Implementation (Short-term)

1. **Complete package structure fix:**
   ```bash
   # Ensure all __init__.py files exist
   touch hailo-apps/hailo_apps/__init__.py
   touch hailo-apps/hailo_apps/python/__init__.py
   touch hailo-apps/hailo_apps/python/pipeline_apps/__init__.py
   
   # Restart service
   sudo systemctl restart hailo-clip.service
   ```

2. **Verify import works:**
   ```bash
   sudo -u hailo-clip /opt/hailo-clip/venv/bin/python3 -c \
     "from hailo_apps.python.pipeline_apps.clip.clip import CLIP; print('Success')"
   ```

3. **Implement real inference in stub class:**
   - Use `run_text_encoder_inference()` from `clip_text_utils.py` for text encoding
   - Implement image encoding using Hailo HEF file for CLIP image encoder
   - Load proper model files (tokenizer, embeddings, projection matrix)

**Pros:** Minimal changes, keeps service architecture as designed  
**Cons:** Requires understanding Hailo inference API, finding/downloading HEF files

### Option B: Redesign Service (Long-term)

1. **Refactor service to use GStreamer pipeline approach:**
   - Integrate `GStreamerClipApp` instead of expecting simple class
   - Adapt REST API to work with pipeline outputs
   - Handle video stream vs. single-image inference

**Pros:** Uses hailo-apps as designed  
**Cons:** Major architectural change, complex GStreamer integration

### Option C: Extract Utilities (Middle ground)

1. **Build minimal wrapper using hailo-apps utilities:**
   - Use `text_image_matcher` singleton
   - Use `run_text_encoder_inference()` directly
   - Implement image encoder using Hailo SDK directly
   - Keep service architecture

**Pros:** Uses proven utilities, keeps service simple  
**Cons:** Still requires HEF file handling and Hailo SDK knowledge

---

## Required Resources for Full Implementation

### Model Files Needed

1. **CLIP Image Encoder HEF:**
   - Model: `clip_resnet_50x4_image_encoder.hef` or similar
   - Location: Unknown (not in hailo-apps, need to download/compile)
   
2. **CLIP Text Encoder HEF:**
   - Model: `clip_resnet_50x4_text_encoder.hef`
   - Location: Referenced in `clip_text_utils.py` but path unknown

3. **Tokenizer and Embeddings:**
   - `clip_tokenizer.json` (CLIP tokenizer)
   - `token_embedding_lut.npy` (Token embedding lookup table)
   - `text_projection.npy` (Text projection matrix)
   - Location: Should be in `setup/` directory per documentation
   - Status: **Missing** (README says "no longer included")

### Documentation References

From [hailo-apps/hailo_apps/python/pipeline_apps/clip/README.md](README.md):

> **Important Note**
> 
> **The scripts to generate the tokenizer, token embedding LUT, and text projection matrix are no longer included in this repository.**
> 
> You must obtain the following files yourself and place them in the `setup/` directory:
> - `clip_tokenizer.json` (CLIP tokenizer)
> - `token_embedding_lut.npy` (Token embedding lookup table)
> - `text_projection.npy` (Text projection matrix)

### Hailo Model Zoo

CLIP models in `networks.json`:
```json
"zero_shot_classification": {
  "clip_vit_l_14_laion2B_image_encoder": {
    "arch": ["hailo8"],
    "source": "cs",
    "hefs": ["clip_vit_l_14_laion2B_image_encoder.hef"],
    "group": "zero_shot_classification",
    "description": "image encoder"
  },
  "clip_text_encoder_vit_l_14_laion2B": {
    "arch": ["hailo8"],
    "source": "cs",
    "hefs": ["clip_vit_l_14_laion2B_image_encoder.hef"],
    "description": "clip text encoder"
  }
}
```

**Note:** Only ViT-L-14 models listed, not ResNet-50x4 that service expects

---

## Recommendations

**Immediate (to get service functional):**
1. Complete `__init__.py` file creation and test import
2. If import succeeds with stub class, service will at least start without errors
3. Document that it's using mock/placeholder implementation

**Short-term (for actual inference):**
1. Research how to obtain or compile CLIP ResNet-50x4 HEF files for Hailo-10H
2. Obtain tokenizer and projection matrices (from HuggingFace or OpenAI CLIP)
3. Implement real `encode_image()` using Hailo inference (similar to `run_text_encoder_inference()`)
4. Implement real `encode_text()` using existing `run_text_encoder_inference()` utility

**Long-term (for production):**
1. Consider whether class-based API is the right approach vs. GStreamer pipeline
2. Evaluate if service should support multiple CLIP model variants
3. Add model downloading/management to installer
4. Create comprehensive tests with known image/text pairs

---

## Questions for User/Team

1. **Model Files:** Where should we source the CLIP ResNet-50x4 HEF and support files?
2. **Architecture:** Should we stick with the class-based service API or adopt GStreamer pipelines?
3. **Model Variant:** Is ResNet-50x4 correct or should we use ViT-L-14 (which is in networks.json)?
4. **Scope:** Is a working stub (mock) acceptable initially, or is real inference required now?
5. **Testing:** What test images and expected results can we use to validate correct inference?

---

## Appendix: File Locations

```
Service files:
- /opt/hailo-clip/venv/                          # Virtual environment
- /opt/hailo-clip/hailo_clip_service.py          # Main service script
- /etc/hailo/hailo-clip.yaml                     # Configuration
- /etc/systemd/system/hailo-clip.service         # Systemd unit

hailo-apps submodule:
- /home/gregm/raspberry_pi_hailo_ai_services/hailo-apps/
- /home/gregm/.../hailo-apps/hailo_apps/python/pipeline_apps/clip/
  ├── clip.py                      # Modified with stub CLIP class
  ├── clip_pipeline.py             # GStreamer pipeline app
  ├── clip_text_utils.py           # Text encoding utilities
  ├── text_image_matcher.py        # Matching logic
  └── __init__.py                  # Empty

Logs:
- journalctl -u hailo-clip.service -f
```

---

**Report generated:** January 31, 2026  
**Last service restart:** 20:57:27  
**Service PID:** 24761
