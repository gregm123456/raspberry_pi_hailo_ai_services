# Hailo Ollama Service Architecture

## Purpose

Deploy the upstream `hailo-ollama` server as a managed systemd service on Raspberry Pi 5 + Hailo-10H, exposing an Ollama-compatible API at port 11434.

## Constraints

- **Device access:** `/dev/hailo0` must be present and accessible by the service user.
- **RAM budget:** ~5–6 GB available for services on Pi 5; default `MemoryMax=4G`.
- **Thermals:** CPU throttles near 80°C; sustained inference may reduce throughput.
- **Concurrency:** Multiple Hailo services can run, but contention may occur.

## Components

```
systemd: hailo-ollama.service
 ├─ ExecStart: hailo-ollama
 ├─ User: hailo-ollama
 ├─ XDG_CONFIG_HOME=/etc/xdg
 ├─ XDG_DATA_HOME=/var/lib
 ├─ Config JSON: /etc/xdg/hailo-ollama/hailo-ollama.json
 └─ Data dir: /var/lib/hailo-ollama
```

## Configuration Flow

1. Operator edits `/etc/hailo/hailo-ollama.yaml`.
2. `render_config.py` converts YAML to `/etc/xdg/hailo-ollama/hailo-ollama.json`.
3. systemd exports XDG variables so `hailo-ollama` reads the JSON and writes model data to `/var/lib/hailo-ollama`.

## systemd Unit Choices

- **Type:** `simple` (upstream does not `sd_notify`)
- **Restart:** `Restart=always`, `RestartSec=5`
- **StateDirectory:** `hailo-ollama` to ensure `/var/lib/hailo-ollama` is owned by the service user
- **Resource limits:** `MemoryMax=4G`, `CPUQuota=80%` (tunable)

## Known Limitations

1. Port conflicts if 11434 is already bound by another process
2. Large models can exhaust RAM; adjust model size or memory limits
3. First inference after pull can be slow due to model load

## Future Improvements

- systemd drop-in override support for resource tuning
- Optional reverse proxy with TLS termination
- Optional warmup model selection via config
