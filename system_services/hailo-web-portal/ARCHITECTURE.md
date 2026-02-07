# Hailo Web Portal Architecture

## Purpose

Provide a unified, full-featured UI for testing all Hailo AI system services without writing curl commands.

## Constraints

- Raspberry Pi 5 memory budget: keep portal <200 MB.
- Hailo device contention: block Ollama if other services are active.
- Local-only access: bind to `127.0.0.1`.

## Components

```
┌───────────────────────────────────────────────┐
│ Gradio UI (port 7860)                         │
│ - Tabs per service                            │
│ - File uploads for image/audio                │
│ - Full parameter coverage                     │
└───────────────────────────────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────────┐
│ FastAPI backend                               │
│ - /api/status (device status)                 │
│ - /api/services/* (systemctl wrapper)         │
│ - Background polling task                     │
└───────────────────────────────────────────────┘
                     │
                     ▼
┌───────────────────────────────────────────────┐
│ Systemd-managed services                      │
│ - hailo-clip, hailo-vision, hailo-ollama, ...  │
└───────────────────────────────────────────────┘
```

## Runtime Model

- Python venv in `/opt/hailo-web-portal/venv`.
- Systemd unit starts the portal with `uvicorn` via `app.py`.
- Device status is polled every 3 seconds to keep the UI current.

## Ollama Conflict Policy

- Starting `hailo-ollama` is blocked when other Hailo services are running.
- The portal does not auto-stop services, it only reports conflicts.

## Resource Limits

- `MemoryMax=200M`
- `CPUQuota=20%`

## Known Limitations

- No authentication (assumes local access only).
- Service control requires passwordless sudo for `systemctl`.
- Streaming endpoints are exposed but rendered as raw text.

## Future Improvements

- Add optional reverse-proxy auth for remote access.
- Add request history and comparison views.
- Add export buttons for JSON and media outputs.
