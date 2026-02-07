# Hailo Web Portal API

Base URL: `http://localhost:7860`

These endpoints are provided by the FastAPI backend that powers the portal UI.

## GET /api/status

Returns the latest device status from `hailo-device-status`.

**Response (200 OK):**
```json
{
  "status": "ok",
  "temperature_c": 46.2,
  "hailo": {
    "loaded_networks": ["clip", "depth"]
  }
}
```

## GET /api/services/status

Returns systemd status for known services.

**Response (200 OK):**
```json
{
  "hailo-device-manager": "running",
  "hailo-clip": "running",
  "hailo-vision": "stopped",
  "hailo-ollama": "stopped"
}
```

## POST /api/services/start/{service_name}

Start a systemd service.

**Response (200 OK):**
```json
{"status": "ok"}
```

**Error (200 OK, with error status):**
```json
{
  "status": "error",
  "message": "Cannot start hailo-ollama while other services are running: hailo-clip"
}
```

## POST /api/services/stop/{service_name}

Stop a systemd service.

**Response (200 OK):**
```json
{"status": "ok"}
```

## POST /api/services/restart/{service_name}

Restart a systemd service.

**Response (200 OK):**
```json
{"status": "ok"}
```

## Notes

- The portal only binds to `127.0.0.1` by default.
- Service control relies on passwordless `sudo systemctl` permissions for the `hailo` user.
