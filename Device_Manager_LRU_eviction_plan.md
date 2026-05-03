# Device Manager LRU Eviction — Implementation Plan

## Problem

The Hailo-10H has 8 GB of dedicated VRAM. When the device manager has multiple large models
loaded simultaneously (particularly hailo-vision's Qwen2-VL-2B at ~4–5 GB), loading an
additional model fails with:

```
HAILO_RESOURCE_EXHAUSTED: Failed to create infer model context.
Not enough resources on device.
```

Currently the device manager returns this error to the requesting service with no recovery
action. The operator must manually stop services and restart the device manager to clear VRAM.
This is incompatible with the project's goal of transparent concurrent multi-service operation.

## Solution: LRU Eviction on RESOURCE_EXHAUSTED

When a `load_model` request fails because of resource exhaustion, automatically evict the
least-recently-used (LRU) model from VRAM and retry the load. Repeat up to a configurable
maximum number of evictions before giving up.

`ModelEntry` already tracks `last_used` (updated in `_infer()`), so the LRU selection
requires only sorting the existing registry — no schema changes.

---

## Architecture

### Data Flow (current)

```
Client → load_model(path, type, params)
           ↓
       _load_model()
           ↓
       handler.load(vdevice, path, params)  ← raises exception on RESOURCE_EXHAUSTED
           ↓
       return {"error": ...}                ← propagated back to client
```

### Data Flow (with LRU eviction)

```
Client → load_model(path, type, params)
           ↓
       _load_model()
           ↓
       handler.load(vdevice, path, params)
           ↓ (RESOURCE_EXHAUSTED exception)
       _evict_lru()                          ← unload LRU entry, log it
           ↓
       handler.load(vdevice, path, params)   ← retry
           ↓ (success or RESOURCE_EXHAUSTED again → repeat up to max_evictions)
       return result
```

---

## Implementation

### 1. Add `_is_resource_exhausted()` helper

The hailo_platform raises an exception whose string representation contains
`"HAILO_RESOURCE_EXHAUSTED"`. Isolating this check makes the condition easy to update if
the SDK changes the exception type in a future release.

```python
@staticmethod
def _is_resource_exhausted(exc: Exception) -> bool:
    """Return True if the exception indicates Hailo VRAM is full."""
    return "HAILO_RESOURCE_EXHAUSTED" in str(exc)
```

Place inside `HailoDeviceManager`.

### 2. Add `_evict_lru()` method

```python
def _evict_lru(self) -> Optional[str]:
    """
    Unload the least-recently-used model from VRAM.

    Returns the evicted model key, or None if the registry is empty.
    """
    if not self.loaded_models:
        return None

    lru_key = min(self.loaded_models, key=lambda k: self.loaded_models[k].last_used)
    entry = self.loaded_models.pop(lru_key)

    try:
        handler = self._get_handler(entry.model_type)
        handler.unload(entry.model)
        logger.info(
            "LRU eviction: unloaded %s (%s), last used %.1fs ago",
            entry.model_path,
            entry.model_type,
            time.time() - entry.last_used,
        )
    except Exception as e:
        logger.warning("LRU eviction unload error (ignored): %s", e)

    return lru_key
```

Place inside `HailoDeviceManager`.

### 3. Modify `_load_model()` to retry after eviction

Replace the current `try/except` block in `_load_model()`:

**Current code (lines ~1044–1066):**
```python
try:
    handler = self._get_handler(model_type)
    logger.info("Loading model: %s (%s)", model_path, model_type)
    model = handler.load(self.vdevice, model_path, model_params)
    now = time.time()
    self.loaded_models[key] = ModelEntry(...)
    ...
    return response
except Exception as e:
    logger.error("Failed to load model %s: %s", model_path, e)
    return {"error": ...}
```

**Replace with:**
```python
MAX_EVICTIONS = 3  # module-level constant

...

# inside _load_model(), after the "already loaded" early-return:
evictions = 0
while True:
    try:
        handler = self._get_handler(model_type)
        logger.info("Loading model: %s (%s)", model_path, model_type)
        model = handler.load(self.vdevice, model_path, model_params)
        now = time.time()
        self.loaded_models[key] = ModelEntry(
            model_type=model_type,
            model_path=model_path,
            model=model,
            loaded_at=now,
            last_used=now,
        )
        response = {
            "status": "ok",
            "model_path": model_path,
            "model_type": model_type,
            "message": "Model loaded",
        }
        if model_type == "ocr":
            response["model_info"] = {
                "detection_input_shape": list(model.detection_input_shape),
            }
        return response

    except Exception as e:
        if self._is_resource_exhausted(e) and evictions < MAX_EVICTIONS:
            evicted = self._evict_lru()
            if evicted is None:
                logger.error(
                    "RESOURCE_EXHAUSTED loading %s but no models to evict", model_path
                )
                return {"error": f"RESOURCE_EXHAUSTED and no models available to evict: {e}"}
            evictions += 1
            logger.warning(
                "RESOURCE_EXHAUSTED loading %s — evicted LRU model %s (attempt %d/%d)",
                model_path, evicted, evictions, MAX_EVICTIONS,
            )
            # Loop and retry
        else:
            logger.error("Failed to load model %s: %s", model_path, e)
            return {"error": f"load failed: {e}"}
```

### 4. Add `MAX_EVICTIONS` module constant

Near the top of `hailo_device_manager.py`, alongside `DEFAULT_SOCKET_PATH`:

```python
# Maximum number of LRU evictions attempted before giving up on a load_model request.
DEFAULT_MAX_EVICTIONS = 3
```

Make it configurable via environment variable (same pattern as other settings):

```python
self.max_evictions = _get_env_int("HAILO_DEVICE_MAX_EVICTIONS", DEFAULT_MAX_EVICTIONS)
```

Then use `self.max_evictions` instead of the module constant in `_load_model()`.

### 5. Surface evictions in the status API (optional but useful)

Add a counter to `HailoDeviceManager.__init__`:

```python
self._total_evictions: int = 0
```

Increment in `_evict_lru()`:

```python
self._total_evictions += 1
```

Add to the HTTP status response:

```python
"total_lru_evictions": self._total_evictions,
```

---

## Edge Cases and Mitigations

| Case | Behavior |
|---|---|
| Evicting a model that is mid-inference | Not possible — `_load_model` and `_infer` both run in the single-threaded `ThreadPoolExecutor`, so no concurrency between load and infer. |
| Evicting `hailo-vision`'s VLM in the middle of a long chat session | The model is evicted; the next `infer` request for it will trigger a `load_model` which reloads it (cold start). Chat history in the client is unaffected; model context is lost. This is acceptable since VLM chat state is managed by the client (hailo-vision service), not the device manager. |
| CLIP has two HEFs but one `ModelEntry` | `ClipHandler.unload()` already releases both `image_configured_model` and `text_configured_model`. Evicting the single CLIP entry frees both HEFs. ✅ |
| Evicting the model that was just requested | Cannot happen — the target model is not in `loaded_models` yet when `_evict_lru()` is called (it failed during `handler.load()`). |
| All evictions still insufficient (e.g., hailo-vision alone exceeds VRAM) | After `MAX_EVICTIONS` attempts the error is returned to the client. The client service logs it and enters an error state. |
| hailo-ollama (exclusive VDevice) | Not managed by the device manager; unaffected by this change. |

---

## Testing Plan

### Unit test (device_manager/test_lru_eviction.py — new file)

1. Populate `manager.loaded_models` with mock entries having staggered `last_used` timestamps.
2. Call `_evict_lru()` and assert the oldest-`last_used` entry was removed.
3. Verify `handler.unload()` was called on the correct mock model.
4. Test `_is_resource_exhausted()` with matching and non-matching exception strings.

### Integration test

1. With hailo-vision running (large VRAM footprint), attempt to start hailo-clip.
2. Observe device manager log: expect `"LRU eviction: unloaded ... last used Xs ago"`.
3. Confirm hailo-clip loads successfully.
4. Confirm hailo-vision reloads automatically on next inference request (lazy reload).

### Regression test

1. Run `device_manager/test_concurrent_services.py` — all existing tests must still pass.

---

## Configuration Reference

| Environment variable | Default | Description |
|---|---|---|
| `HAILO_DEVICE_MAX_EVICTIONS` | `3` | Max LRU evictions before returning an error |

Set in `/etc/systemd/system/hailo-device-manager.service` under `[Service]`:

```ini
Environment="HAILO_DEVICE_MAX_EVICTIONS=3"
```

---

## Files to Modify

| File | Change |
|---|---|
| `device_manager/hailo_device_manager.py` | Add `DEFAULT_MAX_EVICTIONS`, `_is_resource_exhausted()`, `_evict_lru()`, modify `_load_model()`, add `max_evictions` to `__init__`, add eviction counter to status |
| `device_manager/hailo-device-manager.service` | Add `HAILO_DEVICE_MAX_EVICTIONS` env var (optional, documents the default) |
| `device_manager/API_SPEC.md` | Document new `total_lru_evictions` field in status response |
| `reference_documentation/vram_budget.md` | Update "Long-term fix" note to say eviction is implemented |

---

## Why This Is the Right Fix

The project goal (per `README.md`) is:

> *Services become lightweight clients communicating via Unix socket, enabling concurrent
> operation without device conflicts.*

Manual subset management (stopping services before starting others) breaks this goal — it
requires operator knowledge of VRAM budgets and creates coordination friction. LRU eviction
restores transparent concurrent operation: any service can call `load_model` at any time and
the device manager will make room automatically, with the only observable effect being a
slightly longer load time for the evicted model's next request.

The `last_used` field already exists in `ModelEntry` precisely for this purpose. This plan
completes the loop.

---

*Created: May 2026*  
*See also: [reference_documentation/vram_budget.md](reference_documentation/vram_budget.md)*
