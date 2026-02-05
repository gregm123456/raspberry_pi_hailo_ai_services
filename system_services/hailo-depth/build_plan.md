# Hailo Depth Service Rework Plan

This plan reworks the prototype hailo-depth service into a supportable, production-style system service that matches the patterns used by hailo-clip, hailo-ocr, hailo-vision, hailo-pose, and hailo-whisper. It prioritizes:

- Model acquisition in the installer
- Isolated Python runtime in `/opt/hailo-depth/venv`
- Vendored `hailo-apps` for stable model and postprocess resolution
- Standard REST patterns and external input support
- Monocular and stereo depth support with compatible output formats

## Goals

1. Ship a robust systemd service with predictable runtime paths and permissions.
2. Use the hailo-apps depth pipeline and postprocess artifacts rather than placeholder code.
3. Support external inputs (multipart, JSON base64, image URL) by default.
4. Keep local file path inputs optional and disabled by default (test-only).
5. Provide depth outputs compatible with common tooling (NPZ, PNG, 16-bit grayscale).
6. Match documentation and operational standards of other services in this repo.

## Non-Goals

- Building a full video pipeline service (GStreamer) in this iteration.
- Real-time streaming or WebRTC interfaces.
- A batch/queue processing subsystem (can be a future enhancement).

## Architecture Alignment (Existing Services)

The implementation should align with patterns used in:

- hailo-clip: vendored hailo-apps, /opt venv, YAML->JSON config
- hailo-ocr: model downloads in installer, resources in /var/lib
- hailo-vision: OpenAI-compatible patterns, model warmup
- hailo-pose: aiohttp REST service, config rendering, readiness endpoints
- hailo-whisper: multipart uploads, OpenAI-compatible endpoints

## Target Runtime Layout

- Code and venv: `/opt/hailo-depth/`
	- `/opt/hailo-depth/venv/`
	- `/opt/hailo-depth/vendor/hailo-apps/`
	- `/opt/hailo-depth/hailo_depth_server.py`
- Config (YAML source): `/etc/hailo/hailo-depth.yaml`
- Config (JSON runtime): `/etc/xdg/hailo-depth/hailo-depth.json`
- State/resources: `/var/lib/hailo-depth/`
	- `/var/lib/hailo-depth/resources/models/`
	- `/var/lib/hailo-depth/resources/postprocess/`
	- `/var/lib/hailo-depth/cache/`

## Model and Resource Strategy

### Required Artifacts

- Monocular: `scdepthv3.hef`
- Stereo: `stereonet.hef`
- Postprocess: `libdepth_postprocess.so`
- Postprocess function: `filter_scdepth`

### Acquisition Requirements

The installer must download all required artifacts and place them into
`/var/lib/hailo-depth/resources/` without relying on any developer home
directory paths. This mirrors the hailo-ocr/hailo-vision installation
approach and ensures the service is fully portable and supportable.

### Model Resolution Logic

The service should resolve model and postprocess paths in this order:

1. Explicit paths in config (if set)
2. `/var/lib/hailo-depth/resources/` (default)
3. Vendored hailo-apps fallback resolution

This ensures predictable production behavior while keeping developer
flexibility during testing.

## API Design (Standard-Conformant)

### Endpoints (v1)

- `GET /health`
- `GET /health/ready`
- `GET /v1/info`
- `GET /v1/models` (list supported depth models)
- `POST /v1/depth/estimate`
- Optional: `POST /v1/models/load` and `POST /v1/models/unload`

### Inputs (External-First)

`POST /v1/depth/estimate` should accept:

1. `multipart/form-data`
	 - `image` (required)
	 - `image_right` (required for stereo)
	 - `output_format`, `normalize`, `colormap`

2. `application/json`
	 - `image` (base64 or data URI)
	 - `image_right` (base64 or data URI, stereo)
	 - `image_url` (http/https)
	 - `image_right_url` (http/https)

3. Optional local path input (disabled by default)
	 - `image_path` and `image_right_path`
	 - gated by config flag: `input.allow_local_paths=false` by default

### Output Formats

Support the following output modes:

- `numpy`: base64-encoded NPZ (`depth_map`)
- `image`: base64-encoded PNG (`depth_image`)
- `both`
- `depth_png_16`: base64-encoded 16-bit grayscale PNG for compatibility

### Output Metadata

Include standard metadata and optional stats:

- `model`, `model_type`, `input_shape`, `depth_shape`
- `inference_time_ms`, `normalized`
- `stats` (optional): `min`, `max`, `mean`, `p95`

The `stats` field mirrors the depth example logic (average depth
with outlier rejection) and provides a portable summary for clients.

## Service Behavior

### Model Lifecycle

- Default: load model at startup and keep resident (`keep_alive: -1`).
- Optional: unload after idle timeout or per request.
- Optional explicit load/unload endpoints for manual control.

### Concurrency

- Single inference at a time (serialize NPU access), multi-connection async.
- Use aiohttp with an inference lock similar to other services.

### Security Defaults

- No authentication by default (local trusted network model).
- Provide explicit notes for reverse proxy if needed.

## Configuration Schema (YAML)

### Required

```yaml
server:
	host: 0.0.0.0
	port: 11436

model:
	name: scdepthv3
	type: monocular
	keep_alive: -1

output:
	format: both
	colormap: viridis
	normalize: true
	include_stats: true
	depth_png_16: false
```

### Optional

```yaml
input:
	allow_local_paths: false
	allow_image_url: true
	max_image_mb: 50

resources:
	model_dir: /var/lib/hailo-depth/resources/models
	postprocess_dir: /var/lib/hailo-depth/resources/postprocess

resource_limits:
	memory_max: "3G"
	cpu_quota: "80%"
```

## Systemd Unit Requirements

Follow the hardened template used by other services:

- `User=hailo-depth`, `Group=hailo-depth`
- `StateDirectory=hailo-depth`
- `XDG_CONFIG_HOME=/etc/xdg`, `XDG_DATA_HOME=/var/lib`
- `HAILO_PRINT_TO_SYSLOG=1`, `PYTHONUNBUFFERED=1`
- `MemoryMax=3G`, `CPUQuota=80%`
- `PrivateTmp=yes`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`
- `ReadWritePaths=/var/lib/hailo-depth /etc/xdg/hailo-depth`

## Installer Requirements

The installer must:

1. Validate Hailo driver presence and `/dev/hailo0`.
2. Create system user and group (`hailo-depth`).
3. Add service user to Hailo device group.
4. Create `/opt/hailo-depth/` and `/var/lib/hailo-depth/`.
5. Create venv at `/opt/hailo-depth/venv`.
6. Vendor `hailo-apps` to `/opt/hailo-depth/vendor/hailo-apps`.
7. Patch vendored paths to resolve models from `/var/lib/hailo-depth/resources`.
8. Download HEFs and postprocess `.so` to `/var/lib/hailo-depth/resources`.
9. Render YAML -> JSON config.
10. Install and enable systemd unit.
11. Optional warmup (`--warmup-model`).

## Implementation Phases

### Phase 1: Infrastructure and Packaging

- Move runtime to `/opt/hailo-depth` with venv
- Vendor hailo-apps
- Update systemd unit to use venv Python
- Update config rendering and XDG paths

Deliverable: service starts and reads config from `/etc/xdg`.

### Phase 2: Model Acquisition

- Installer downloads HEFs and postprocess `.so`
- Path resolution validated at service startup

Deliverable: service can locate and load model artifacts under `/var/lib`.

### Phase 3: Real Inference Integration

- Replace placeholder depth generation with hailo-apps depth inference
- Add monocular/stereo model selection
- Validate postprocess output and resizing behavior

Deliverable: actual depth maps from Hailo-10H inference.

### Phase 4: API Enhancements

- Add image URL inputs
- Gate local path inputs by config
- Add depth_png_16 and stats output

Deliverable: external-first API that supports common clients.

### Phase 5: Docs + Tests

- Update README/API_SPEC/ARCHITECTURE/TROUBLESHOOTING
- Add integration tests for multipart, JSON, and URL inputs
- Add tests for stereo vs monocular selection

Deliverable: consistent documentation and basic test coverage.

## Acceptance Criteria

1. `sudo ./install.sh` installs venv, downloads models, and starts service.
2. `curl http://localhost:11436/health` returns `model_loaded=true` after warmup.
3. `POST /v1/depth/estimate` works for:
	 - multipart upload
	 - JSON base64
	 - image_url
4. Stereo mode accepts `image_right` and returns stereo depth.
5. Outputs support `numpy`, `image`, `both`, and `depth_png_16`.
6. All docs match actual behavior and file paths.
7. Service runs as `hailo-depth` with hardened systemd settings.

## File Changes (Planned)

Core service:
- `system_services/hailo-depth/hailo_depth_server.py`

Installer and systemd:
- `system_services/hailo-depth/install.sh`
- `system_services/hailo-depth/hailo-depth.service`

Config and rendering:
- `system_services/hailo-depth/config.yaml`
- `system_services/hailo-depth/render_config.py`

Docs:
- `system_services/hailo-depth/README.md`
- `system_services/hailo-depth/API_SPEC.md`
- `system_services/hailo-depth/ARCHITECTURE.md`
- `system_services/hailo-depth/TROUBLESHOOTING.md`

Tests:
- `system_services/hailo-depth/tests/` (new or expanded)

## Open Questions / Decisions to Confirm

1. Confirm preferred default model: `scdepthv3` only, or default to `scdepthv3` with stereo optional.
2. Confirm desired default output format (`both` or `numpy`).
3. Confirm whether we should add explicit `/v1/models/load` and `/v1/models/unload` endpoints.
4. Confirm image URL size limits and allowed domains (any https by default, or allowlist).

## Notes

- Depth values are relative and may be normalized. API and docs should
	emphasize that depth does not represent absolute distances.
- The depth example calculates average depth after removing top 5% outliers;
	this becomes the `stats.p95` and `stats.mean` outputs.
- Keep the service fast and simple: reuse hailo-apps and avoid reimplementing
	postprocess logic in Python.
