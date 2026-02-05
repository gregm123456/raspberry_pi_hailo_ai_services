# Notes: hailo-face vs hailo-scrfd

This document compares the two first-draft face processing system services in this repository: `hailo-face` and `hailo-scrfd`.

**Overview**

- Both services target Raspberry Pi 5 with Hailo-10H NPU acceleration and follow the project pattern: a small Flask REST API, YAML operator-facing config, systemd unit, installer/verify scripts, and optional model warmup.  They are designed as modular, low-overhead system services that can be composed into larger pipelines.

**Similarities**

- Hardware: Hailo-10H NPU, requires Hailo kernel driver.
- Framework: Flask REST API, YAML config, systemd service, dedicated system user, state/config directories under `/var/lib` and `/etc/hailo`.
- Detection: Both use SCRFD for face localization (bounding boxes, confidence) and support configurable thresholds, worker threads, timeouts, model warmup, and resource limits.
- Integration: Both designed to integrate with `hailo-apps` and the Hailo model zoo for HEF/ONNX models and postprocessing.

**Key Differences**

| Aspect | hailo-face | hailo-scrfd |
|---|---|---|
| Primary purpose | End-to-end face recognition: detection → embedding (ArcFace) → database matching / identity management | Specialized face detection + landmarks + alignment (SCRFD) — preprocessing building block |
| Models used | SCRFD (detection) + ArcFace MobileFaceNet (512D embedding) | SCRFD only (variants like `scrfd_2.5g_bnkps` / `scrfd_10g_bnkps`) |
| API endpoints | `/health`, `/v1/detect`, `/v1/embed`, `/v1/recognize`, database management (`/v1/database/*`) | `/health`, `/v1/detect`, `/v1/align` (alignment/crops), annotated image support |
| Persistent DB | Yes — SQLite (`/var/lib/hailo-face/faces.db`) with identity add/remove/list and backup support | No — stateless detection/alignment service |
| Output | Bounding boxes, optional 5-point landmarks, 512D embeddings, recognition matches and similarity scores | Bounding boxes, 5-point landmarks, aligned face crops (112×112), annotated images if requested |
| Port (default) | 5002 | 5001 |
| Resource footprint | Higher (single service loads two models + DB) — config uses MemoryMax=3G | Lower (single model) — config uses MemoryMax=2G |
| Integration role | Standalone recognition service (suitable for identity verification and management) | Pipeline component feeding recognition services (detect → align → embed) |

**Files and code locations (citations)**

- `hailo-face` service:
  - [system_services/hailo-face/README.md](system_services/hailo-face/README.md)
  - [system_services/hailo-face/hailo_face_service.py](system_services/hailo-face/hailo_face_service.py)
  - [system_services/hailo-face/config.yaml](system_services/hailo-face/config.yaml)
  - [system_services/hailo-face/hailo-face.service](system_services/hailo-face/hailo-face.service)

- `hailo-scrfd` service:
  - [system_services/hailo-scrfd/README.md](system_services/hailo-scrfd/README.md)
  - [system_services/hailo-scrfd/hailo_scrfd_service.py](system_services/hailo-scrfd/hailo_scrfd_service.py)
  - [system_services/hailo-scrfd/config.yaml](system_services/hailo-scrfd/config.yaml)
  - [system_services/hailo-scrfd/hailo-scrfd.service](system_services/hailo-scrfd/hailo-scrfd.service)

- Model-zoo support for demographics (found in the repo):
  - [hailo_model_zoo/hailo_model_zoo/core/postprocessing/age_gender_postprocessing.py](hailo_model_zoo/hailo_model_zoo/core/postprocessing/age_gender_postprocessing.py) — age/gender postprocessing + visualization
  - [hailo_model_zoo/hailo_model_zoo/core/eval/age_gender_evaluation.py](hailo_model_zoo/hailo_model_zoo/core/eval/age_gender_evaluation.py) — evaluation for age/gender models
  - [hailo_model_zoo/hailo_model_zoo/core/datasets/parse_utkfaces.py](hailo_model_zoo/hailo_model_zoo/core/datasets/parse_utkfaces.py) — UTKFaces dataset parser used for age/gender experiments

**Use cases**

- `hailo-face` is appropriate where the system must provide identity-related functionality: enroll identities, extract embeddings, and perform recognition or verification against a persistent store.
- `hailo-scrfd` is appropriate where you need a lightweight, fast face detector and aligner for preprocessing, real-time video pipelines, or when detection/landmarking should be separated (for scaling or resource isolation).

**Limitations & considerations**

- Both are first-draft stubs: authentication, rate-limiting, hardened error handling, and privacy/consent controls are not present by default.
- Accuracy and fairness depend on model variants and training data — test across the target demographics and lighting/pose conditions.
- For emotion/expression analysis there is no dedicated service in these stubs; you can approximate expressions with CLIP zero-shot prompts (see `hailo-clip`) or integrate a dedicated FER model into the model zoo and add endpoints.

**Recommendation / How to compose them**

1. Use `hailo-scrfd` as the front-line detector/aligner (port 5001). Configure `alignment.output_size: 112` and `detection.max_faces` as needed.
2. Feed aligned crops to `hailo-face` `/v1/embed` (port 5002) to extract 512D embeddings.
3. Use `hailo-face` `/v1/recognize` for database matching, or call an external matching service if you prefer to centralize identity storage.

If you'd like, I can: (a) add a small wrapper that proxies `hailo-scrfd` → `hailo-face` to demonstrate the pipeline, or (b) add an emotion attribute endpoint by wiring a model from the model zoo. Which would you prefer?
