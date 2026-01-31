---
name: documentation
description: Documentation standards for Hailo system services
---

# System Service Documentation

This skill defines documentation standards and templates for each system service in this repository.

## Documentation Files

Every service (`system_services/<service-name>/`) must include:

### 1. README.md
**Purpose:** Overview, quick start, basic configuration

**Sections:**
- Service description (one paragraph)
- Prerequisites (what must be installed first)
- Quick installation (`./install.sh`)
- Configuration (environment variables, config file)
- Basic usage (curl example, systemctl commands)
- Troubleshooting (common issues)
- Links to detailed docs

**Example:**

```markdown
# Hailo Ollama Service

Deploys Ollama LLM inference as a systemd service on Raspberry Pi 5 with Hailo-10H.

## Prerequisites

- Hailo-10 driver installed: `sudo apt install hailo-h10-all`
- Verify: `hailortcli fw-control identify`

## Installation

$ sudo ./install.sh
$ sudo systemctl status hailo-ollama.service
$ curl http://localhost:11434/api/health

## Configuration

Edit `/etc/hailo/ollama.yaml`:
```yaml
port: 11434
model: neural-chat
```

## Troubleshooting

**Service won't start:** Check logs with `sudo journalctl -u hailo-ollama.service -f`
```

### 2. API_SPEC.md (if service exposes API)
**Purpose:** Complete REST API reference

**Sections:**
- Authentication (if required; none for basic setup)
- Base URL
- Endpoints (one per subsection):
  - HTTP method & path
  - Description
  - Query/body parameters (with types)
  - Response format (JSON schema or example)
  - Error responses
  - Example curl commands

**Example:**

```markdown
# Hailo Ollama API

Base URL: `http://localhost:11434`

## GET /api/health

Check service health.

**Response (200 OK):**
```json
{
  "status": "ok",
  "uptime_seconds": 3600
}
```

Error (503): Returns if Hailo device unavailable or thermal throttle active.

**Example:**
```bash
curl http://localhost:11434/api/health | jq
```

## POST /api/chat

Run inference on a model.

**Request:**
- `model` (string): Model name, e.g., "neural-chat"
- `messages` (array): Chat history
  - `role` (string): "user" or "assistant"
  - `content` (string): Message text

**Response (200 OK):**
```json
{
  "role": "assistant",
  "content": "Response text...",
  "model": "neural-chat",
  "eval_count": 42
}
```

**Example:**
```bash
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "neural-chat", "messages": [{"role": "user", "content": "Hello"}]}' | jq
```
```

### 3. ARCHITECTURE.md
**Purpose:** Design decisions, constraints, internal structure

**Sections:**
- Service purpose and responsibilities
- Design constraints (Hailo single-access, RAM budget, thermal limits)
- Component architecture (how service is structured)
- Deployment model (systemd Type, restart policy)
- Resource limits and expected usage
- Known limitations
- Future improvements

**Example:**

```markdown
# Hailo Ollama Service Architecture

## Purpose

Expose LLM inference via REST API, running continuously as systemd service.

## Constraints

- **Single Hailo access:** Only one process accesses `/dev/hailo0`; service is exclusive
- **RAM budget:** 2GB allocated for model caching + inference (~5-6GB available on Pi 5)
- **Thermal limits:** CPU throttles at 80°C; complete shutdown at ~85°C
- **CPU:** All 4 cores available but shared with OS and other processes

## Architecture

```
┌─ systemd hailo-ollama.service ─┐
│                                 │
│  Ollama LLM Runtime             │
│  ├── Flask/Starlette REST API   │
│  ├── Model loader               │
│  └── Hailo-10 inference engine  │
│                                 │
│  Listens: localhost:11434       │
│  User: hailo (dedicated)        │
└─────────────────────────────────┘
        │
        ├─→ /dev/hailo0 (exclusive access)
        ├─→ /var/lib/ollama/ (model cache)
        └─→ journald (logging)
```

## Resource Limits

- `MemoryLimit=2G` - Prevent swap thrashing
- `CPUQuota=75%` - Reserve 25% for OS
- Graceful degradation at thermal throttle

## Known Limitations

1. Single inference at a time (serial processing)
2. Model loading takes 10-30s (first run)
3. Large models (13B+) may not fit in RAM
4. Thermal throttle reduces inference speed by ~30%

## Future Work

- [ ] Model queueing for batch inference
- [ ] Health-check based auto-restart
- [ ] Prometheus metrics export
- [ ] Model hot-swap without restart
```

### 4. TROUBLESHOOTING.md
**Purpose:** Diagnostic procedures and solutions for common issues

**Format:**
- Problem statement
- Diagnostic steps (commands to run)
- Root causes (likely reasons)
- Solutions (step-by-step fixes)

**Example:**

```markdown
# Troubleshooting Hailo Ollama Service

## Service fails to start

**Diagnostic:**
```bash
sudo systemctl status hailo-ollama.service
sudo journalctl -u hailo-ollama.service -n 50
```

**Root Causes:**
- Hailo device not detected (`/dev/hailo0` missing)
- Insufficient permissions (user `hailo` cannot access device)
- Model directory not writable

**Solutions:**
1. Verify Hailo driver: `hailortcli fw-control identify`
2. Check user/group: `id hailo && ls -l /dev/hailo0`
3. Repair permissions: `sudo chgrp hailo /dev/hailo0 && sudo chmod g+rw /dev/hailo0`
4. Restart: `sudo systemctl restart hailo-ollama.service`

## High latency on first inference

**Expected:** Model loading takes 10-30 seconds first run (pre-caches weights).

**Diagnostic:**
```bash
# Monitor during first inference
sudo journalctl -u hailo-ollama.service -f &
curl -X POST http://localhost:11434/api/chat \
  -d '{"model": "neural-chat", "messages": [{"role": "user", "content": "Hi"}]}'
```

**Solution:** Batch first inference as part of health check to pre-warm model.

## Thermal throttle (temperature >80°C)

**Diagnostic:**
```bash
vcgencmd measure_temp
sudo journalctl -u hailo-ollama.service | grep "503\|throttle"
```

**Root Causes:**
- High ambient temperature
- No active cooling fan
- Continuous high-load inference

**Solutions:**
1. Add active cooling: USB fan to Pi 5 heatsink
2. Reduce batch size or model size
3. Add request queueing + delay between inference calls
4. Increase `CPUQuota` to lower CPU priority (reduce competing load)
```

## Documentation Checklist

Before shipping a new service:

- [ ] README.md covers quick start + configuration
- [ ] API_SPEC.md (if applicable) documents all endpoints with curl examples
- [ ] ARCHITECTURE.md explains design decisions + constraints
- [ ] TROUBLESHOOTING.md covers ≥5 common issues with diagnostic steps
- [ ] Code comments explain non-obvious logic
- [ ] Systemd unit file has comments on key settings
- [ ] Installer script has inline comments for steps
- [ ] All relative paths documented (model dir, config location)
- [ ] External dependencies listed (packages, APIs, files)

## Writing Style

- **Audience:** Developers and users with Linux/systemd familiarity
- **Tone:** Clear, procedural, action-oriented
- **Format:** Use bash code blocks for commands; JSON for API examples
- **Examples:** Include copy-paste-ready curl/systemctl commands
- **Errors:** Explicitly show expected vs. error output

---

**Reference Templates:** See `system_services/hailo-ollama/` for real examples.
