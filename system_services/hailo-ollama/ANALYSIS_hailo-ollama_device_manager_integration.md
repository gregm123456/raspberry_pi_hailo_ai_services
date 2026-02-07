# Analysis: Hailo-Ollama Device Manager Integration Prospects

**Date:** February 6, 2026  
**Author:** Greg  
**Context:** Evaluating integration of `hailo-ollama` service with the `device_manager` architecture for unified Hailo-10H device access and request serialization.

## Executive Summary

It is possible in principle to bring `hailo-ollama` under `device_manager` control, but it is not a straightforward drop-in like the vision/clip/whisper services. `hailo-ollama` is architecturally different because it is a closed-source, self-contained server that owns its own Hailo device lifecycle, model loading, scheduling, and API surface. The `device_manager` is designed to be the single process that owns the VDevice and exposes a narrow, typed RPC for model load/infer/unload. These two models conflict by design.

**Recommendation:** Pursue coexistence with serialization outside the `device_manager` (most realistic). `hailo-ollama` will remain a standalone service that cannot be cleanly folded into the `device_manager` architecture without significant changes from Hailo.

## Architectural Comparison

### Device Ownership Model

**hailo-ollama:**
- Owns the Hailo runtime directly
- Manages model pulls, caching, scheduling, and inference in-process
- Creates its own VDevice connection to `/dev/hailo0`
- Device lifecycle tied to service lifecycle

**device_manager:**
- Centralizes ownership of the single VDevice
- Exports a queue-based RPC for device operations
- Clients are thin and delegate all device ops
- Single process serializes all device access

**Conflict:** `hailo-ollama` expects exclusive device access; `device_manager` expects to be the exclusive owner.

### API Surface

**hailo-ollama:**
- Implements Ollama/OpenAI REST APIs (port 11434)
- Manages model lifecycle internally (pull, load, unload)
- Exposes high-level chat/generate endpoints
- Handles model discovery via manifests

**device_manager:**
- Exposes low-level Unix socket RPC (load_model, infer, unload_model)
- No REST API; clients handle their own API surface
- Model paths are explicit HEF files
- No built-in model discovery or pull mechanism

**Conflict:** `hailo-ollama`'s API is end-user facing; `device_manager`'s is internal service-to-service.

### Model Format and Lifecycle

**hailo-ollama:**
- Uses model manifests from Hailo GenAI Model Zoo
- Models identified by names (e.g., "qwen2:1.5b")
- Pulls models from remote library on demand
- Caches models in `/var/lib/hailo-ollama/models/blobs/`

**device_manager:**
- Expects explicit HEF file paths
- Model types defined by handlers (vlm, clip, etc.)
- No pull mechanism; models must be pre-installed
- Caches loaded models in device memory

**Conflict:** Different model discovery, naming, and storage paradigms.

### Integration Model

**hailo-ollama:**
- Closed-source binary from Hailo Developer Zone
- Not designed to be a thin client
- No visible hooks for external VDevice management

**device_manager:**
- Open Python implementation
- Clients explicitly integrate via `HailoDeviceClient`
- Designed for extensible model handlers

**Conflict:** `hailo-ollama` cannot be refactored to use `device_client.py` like Python services.

## Integration Options Assessment

### Option 1: Coexistence with External Serialization (Recommended)

**Description:** Run `hailo-ollama` as a standalone service alongside `device_manager`. Other services route through `device_manager`. Avoid device contention through service orchestration.

**Pros:**
- Minimal changes required
- Preserves `hailo-ollama`'s existing architecture
- Works operationally with careful scheduling
- Allows parallel development

**Cons:**
- `hailo-ollama` remains a peer that can conflict at runtime
- No true shared-device serialization
- Requires manual conflict avoidance

**Implementation:**
- Systemd ordering: `hailo-ollama` starts after `device_manager`
- Load shedding: Stop `hailo-ollama` when other services need priority
- Monitoring: Check device status before starting inference-heavy services

### Option 2: Device-Level Arbitration via Wrapper

**Description:** A supervisor process pauses/stops `hailo-ollama` or blocks its access when other services are active.

**Pros:**
- Avoids device conflicts without modifying `hailo-ollama`
- Coarse-grained control over device access

**Cons:**
- Not true shared-device serialization
- Hurts latency (service restarts)
- Complex to implement reliably
- Still no unified model caching

**Implementation:**
- Custom systemd service that monitors device usage
- DBus or socket-based coordination between services
- `hailo-ollama` treated as "exclusive mode" service

### Option 3: Full Integration (Requires Hailo Changes)

**Description:** Modify `hailo-ollama` to connect to an externally managed VDevice or use a "device proxy" provided by `device_manager`.

**Pros:**
- True unified device management
- Shared model caching across all services
- Optimal resource utilization

**Cons:**
- Requires Hailo to expose VDevice externalization API
- `hailo-ollama` source code access needed
- Significant architectural changes
- Not currently possible with closed binary

**Implementation:**
- `device_manager` becomes VDevice proxy
- `hailo-ollama` uses device_manager client internally
- Model manifests integrated with device_manager registry

## Current State Assessment

As of February 2026, `hailo-ollama` operates successfully as a standalone systemd service with:
- Bind-mounted model manifests
- XDG-compliant configuration
- Journald logging
- Resource limits (MemoryMax=4G, CPUQuota=80%)

It coexists with other services but requires manual scheduling to avoid device conflicts. The `device_manager` successfully serializes requests for Python-based services (vision, clip, whisper) but cannot control `hailo-ollama`.

## Recommendations

1. **Short-term:** Implement coexistence policy with systemd ordering and load shedding. Document service scheduling requirements in READMEs.

2. **Medium-term:** Request Hailo for VDevice externalization capabilities in future GenAI releases.

3. **Long-term:** If source access becomes available, refactor `hailo-ollama` to use `device_manager` as its device backend.

4. **Alternative:** Consider building a native Ollama-compatible service using `device_manager` and open-source components, avoiding dependency on closed `hailo-ollama`.

## Next Steps

- Draft coexistence policy document
- Test service ordering with `systemctl` dependencies
- Monitor device conflicts in multi-service scenarios
- Engage Hailo Developer Zone for integration feedback

## References

- [hailo-ollama README](README.md)
- [hailo-ollama ARCHITECTURE](ARCHITECTURE.md)
- [device_manager README](../device_manager/README.md)
- [device_manager ARCHITECTURE](../device_manager/ARCHITECTURE.md)
