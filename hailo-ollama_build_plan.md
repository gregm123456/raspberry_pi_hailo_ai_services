
# Hailo-Ollama System Service Build Plan

Date: 2026-01-31

This document is the detailed build plan for a standalone `system_services/hailo-ollama/` sub-project that deploys the upstream `hailo-ollama` server (Ollama-compatible REST API implemented in C++ on HailoRT) as a managed systemd service on Raspberry Pi 5 + Hailo-10H.

The goal is a pragmatic, reliable “system glue” deployment wrapper: systemd unit + idempotent installer + simple config management, without re-implementing the server.

---

## 1) Goals

1. Provide a **standalone deployment mini-project** under `system_services/hailo-ollama/`.
2. Deploy `hailo-ollama` as a **systemd-managed service**:
	- start on boot
	- restart on failure
	- logs in journald
3. Standardize an **Ollama-compatible endpoint** reachable at:
	- base URL: `http://0.0.0.0:11434`
4. Use an **ops-friendly configuration story**:
	- human-edited YAML in `/etc/hailo/`
	- generated upstream JSON config in `/etc/xdg/` (because upstream uses XDG base dirs)
5. Persist models and downloaded blobs in **writable system state storage**:
	- `/var/lib/hailo-ollama` owned by a dedicated system user
6. Fit Raspberry Pi constraints (RAM/CPU/thermals) with sensible defaults and clear tuning knobs.

---

## 2) Non-goals (v1)

1. Do **not** rewrite or proxy the upstream API.
2. Do **not** introduce authentication, multi-tenant access control, or TLS termination in v1.
3. Do **not** ship a curated model set or do mandatory model pre-pulls (optional warmup only).
4. Do **not** attempt to manage the full Hailo stack installation (driver/runtime). We only verify prerequisites.
5. Do **not** guarantee compatibility with all Ollama behaviors beyond the endpoints exposed by upstream `hailo-ollama`.

---

## 3) Inputs / Constraints / Assumptions

### Platform constraints

- Raspberry Pi 5 has limited RAM available for services (~5–6 GB usable after OS overhead).
- Thermal throttling occurs around 80°C; sustained inference can increase CPU temp.
- Hailo device node is typically `/dev/hailo0`.
- Device access can fail if permissions are wrong or the device is missing.

### Hailo-10H “concurrency” reality

Documentation in the repo notes Hailo can support concurrent services; nonetheless, contention can occur.

Plan assumption for robustness:
- The service should tolerate “device busy” / transient failures and systemd should restart it.
- We should not assume exclusive access is always available at startup.

### Upstream `hailo-ollama` behavior we must integrate with

Upstream configuration uses XDG base directories and expects:
- Config file name: `hailo-ollama.json`
- Config directory name: `hailo-ollama`
- Data directory name: `hailo-ollama`

Upstream default config (reference):
- `server.host: 0.0.0.0`
- `server.port: 8000`
- `library.host: dev-public.hailo.ai`
- `library.port: 443`
- `main_poll_time_ms: 200`

This service plan intentionally overrides the port to **11434** for Ollama ecosystem compatibility.

### Deployment choice (already decided)

We will **depend on the Developer Zone Debian package** that installs `hailo-ollama` (no compilation during install).

The service wrapper must:
- validate `hailo-ollama` exists in `PATH`
- provide a helpful error if not installed

---

## 4) High-level architecture

We deploy the upstream server directly and standardize its filesystem and config via XDG environment variables.

```
┌─────────────────────────────────────────┐
│ systemd: hailo-ollama.service           │
│  - runs as hailo-ollama user            │
│  - env sets XDG_* dirs                  │
│  - ExecStart: hailo-ollama              │
│  - logs → journald                      │
└───────────────┬─────────────────────────┘
					 │
					 │ reads config
					 v
		/etc/xdg/hailo-ollama/hailo-ollama.json
					 │
					 │ writes/reads state
					 v
		/var/lib/hailo-ollama/models/{manifests,blob}

API: http://0.0.0.0:11434/...
```

We keep YAML as the operator-facing config format and generate the JSON expected by upstream.

---

## 5) Target project structure (to create)

Create:

```
system_services/
  hailo-ollama/
	 install.sh
	 uninstall.sh
	 hailo-ollama.service
	 config.yaml                 # template copied to /etc/hailo/hailo-ollama.yaml
	 render_config.py            # YAML → /etc/xdg/hailo-ollama/hailo-ollama.json
	 verify.sh                   # quick local verification helper
	 tests/
		test_hailo_ollama_service.py (optional)
```

Documentation files (recommended by repo standards) can be added later, but are not required to execute this build plan unless requested.

---

## 6) Configuration design

### 6.1 Operator-facing YAML

Target path: `/etc/hailo/hailo-ollama.yaml`

Template (stored in repo as `system_services/hailo-ollama/config.yaml`):

```yaml
server:
  host: 0.0.0.0
  port: 11434

library:
  host: dev-public.hailo.ai
  port: 443

main_poll_time_ms: 200

# Optional tuning
resource_limits:
  # systemd unit tuning knobs (installer can apply defaults; advanced users can edit unit override)
  memory_max: "4G"
  cpu_quota: "80%"
```

Notes:
- The upstream server does not read this YAML directly.
- YAML is used so humans can edit a readable file under `/etc/hailo/`.

### 6.2 Generated upstream JSON

Target path: `/etc/xdg/hailo-ollama/hailo-ollama.json`

Generated content must match upstream schema:

```json
{
  "server": {"host": "0.0.0.0", "port": 11434},
  "library": {"host": "dev-public.hailo.ai", "port": 443},
  "main_poll_time_ms": 200
}
```

### 6.3 XDG environment mapping (critical)

We control where upstream reads/writes via systemd environment:

- `XDG_CONFIG_DIRS=/etc/xdg`
- `XDG_CONFIG_HOME=/etc/xdg`
  - so config resolves to `/etc/xdg/hailo-ollama/hailo-ollama.json`
- `XDG_DATA_DIRS=/var/lib`
- `XDG_DATA_HOME=/var/lib`
  - so data resolves to `/var/lib/hailo-ollama/...`

This ensures that runtime “pull” downloads go into a writable state directory and survive reboots.

---

## 7) systemd unit design

Target installed path: `/etc/systemd/system/hailo-ollama.service`

Recommended unit characteristics:

- **Type**: `simple`
  - upstream binary likely does not `sd_notify`; avoid `Type=notify` unless we add a wrapper.
- **User/Group**: `hailo-ollama`
  - dedicated system user, no shell.
- **StateDirectory**: `hailo-ollama`
  - systemd will create `/var/lib/hailo-ollama` and chown it.
- **Restart policy**: `Restart=always`, `RestartSec=5`
- **Networking**: `After=network-online.target`, `Wants=network-online.target`
- **Logging**: journald (default)
- **Resource limits**: optional `MemoryMax=`, `CPUQuota=` tuned for Pi.

Example unit (to be created in the sub-project):

```ini
[Unit]
Description=Hailo Ollama (Ollama-compatible API on Hailo-10H)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

User=hailo-ollama
Group=hailo-ollama

# Ensure writable state dir exists and is owned correctly
StateDirectory=hailo-ollama

# XDG wiring: force config + data locations
Environment=XDG_CONFIG_HOME=/etc/xdg
Environment=XDG_CONFIG_DIRS=/etc/xdg
Environment=XDG_DATA_HOME=/var/lib
Environment=XDG_DATA_DIRS=/var/lib

ExecStart=/usr/bin/env hailo-ollama

Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM

# Optional Pi guardrails (tune as needed)
MemoryMax=4G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

Notes:
- `ExecStart=/usr/bin/env hailo-ollama` avoids hardcoding binary location, but still requires `PATH` to include it (standard under systemd).
- If needed, the installer can detect the absolute path via `command -v hailo-ollama` and substitute a concrete path.

---

## 8) Installer / Uninstaller behavior

### 8.1 Installer goals

`install.sh` must be:
- idempotent (safe to rerun)
- strict-mode bash
- explicit about prerequisites and how to fix missing pieces

### 8.2 Installer responsibilities (detailed)

1. **Preflight checks**
	- Confirm running as root (or via sudo).
	- Verify Hailo runtime/driver presence:
	  - `/dev/hailo0` exists
	  - `hailortcli fw-control identify` succeeds (best-effort check)
	- Verify upstream server exists:
	  - `command -v hailo-ollama` succeeds
	  - If missing: print instructions to install the Developer Zone GenAI Model Zoo Debian package.

2. **Create system user and group**
	- Create system user `hailo-ollama`:
	  - `useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-ollama hailo-ollama`
	- Create group `hailo-ollama` (usually implicit with useradd, but handle both cases).

3. **Device permissions**
	- Check ownership/group of `/dev/hailo0`.
	- Add `hailo-ollama` to the device group (commonly `hailo`).
	- If the device group does not exist, fail with a clear message pointing back to system setup.
	- Avoid permanently chmod’ing `/dev/hailo0` in the installer if that is managed by udev on reboot; prefer group membership.

4. **Install config**
	- Ensure `/etc/hailo/` exists.
	- If `/etc/hailo/hailo-ollama.yaml` does not exist:
	  - copy template from `system_services/hailo-ollama/config.yaml`
	- Ensure `/etc/xdg/hailo-ollama/` exists.
	- Run `render_config.py` to generate `/etc/xdg/hailo-ollama/hailo-ollama.json`.
	  - This should overwrite the JSON every install run so it stays in sync.

5. **Install systemd unit**
	- Copy `hailo-ollama.service` to `/etc/systemd/system/hailo-ollama.service`.
	- `systemctl daemon-reload`
	- `systemctl enable --now hailo-ollama.service`

6. **Post-install verification**
	- Wait briefly for service start.
	- Check:
	  - `systemctl is-active --quiet hailo-ollama.service`
	  - `curl -fsS http://localhost:11434/api/version` (or `/api/tags`) returns success.
	- If verification fails: print `journalctl -u hailo-ollama.service -n 100 --no-pager` hint.

### 8.3 Uninstaller goals

`uninstall.sh` should:
- stop and disable the service
- remove unit file
- optionally remove user/group
- by default, keep `/var/lib/hailo-ollama` (models can be large; avoid surprise deletion)

Provide flags:
- `--purge-data` to remove `/var/lib/hailo-ollama`
- `--remove-user` to remove `hailo-ollama`

---

## 9) Health checks and warmup strategy

### 9.1 Health check endpoint choice

Prefer a fast endpoint that indicates the HTTP server is up:
- `GET /api/version`

Secondary checks:
- `GET /api/tags` (may depend on model state)

### 9.2 Warmup (optional)

Optional warmup modes (installer-controlled):

1. **No warmup** (default)
	- No downloads; minimal side effects.

2. **Pull a default model** (opt-in)
	- Use `/api/pull` with a user-chosen model name.
	- Benefits: avoids first-use latency for demos/installations.
	- Tradeoff: downloads can be large; requires network; might surprise users.

3. **First inference** (opt-in)
	- Use `/api/chat` with a tiny prompt if a model is already present.

---

## 10) Testing strategy

### 10.1 Local smoke test script

Include `verify.sh` under the service project to run on the Pi:

- `systemctl status hailo-ollama.service --no-pager`
- `curl -fsS http://localhost:11434/api/version`
- `ss -lntp | grep 11434` (or `lsof -i :11434`)

### 10.2 Minimal pytest integration test (optional)

If we add tests, keep them pragmatic:

- Skip if `hailo-ollama` binary missing.
- Skip if not running on Linux.
- Skip if `/dev/hailo0` absent.

Core assertions:
- Service active
- HTTP endpoint returns 200

---

## 11) Acceptance criteria (definition of done)

The `system_services/hailo-ollama/` sub-project is “done” when:

1. `sudo ./install.sh` succeeds on a Pi 5 with Hailo-10H and required packages.
2. `systemctl is-enabled hailo-ollama.service` returns enabled.
3. `systemctl is-active hailo-ollama.service` returns active.
4. `curl -fsS http://localhost:11434/api/version` succeeds.
5. Models can be pulled and persisted:
	- After `POST /api/pull`, downloaded artifacts land under `/var/lib/hailo-ollama/models/...`.
6. Logs are visible in journald:
	- `journalctl -u hailo-ollama.service -f` shows service output.
7. Reboot persistence:
	- After reboot, service comes back and state directory remains intact.

---

## 12) Risks and mitigations

1. **Upstream binary path varies**
	- Mitigation: use `/usr/bin/env hailo-ollama` or detect with `command -v`.

2. **Port conflicts (11434 already used)**
	- Mitigation: document port in YAML; allow user to change; installer can detect conflict and warn.

3. **Device permissions fail after reboot**
	- Mitigation: rely on group membership + correct udev rules from Hailo packages; avoid ad-hoc chmod.

4. **Large model downloads fill disk**
	- Mitigation: keep warmup opt-in; document storage path; provide “purge data” uninstall flag.

5. **Thermal throttling impacts performance**
	- Mitigation: recommend cooling and monitoring; expose resource limits as tuning knobs.

---

## 13) Implementation task breakdown (maps to TODO list)

1. Create the `system_services/hailo-ollama/` skeleton with scripts, unit, config template, and renderer.
2. Implement YAML → JSON rendering and ensure XDG variables point to correct locations.
3. Finalize systemd unit with StateDirectory and sensible restart/limits.
4. Implement idempotent `install.sh` and `uninstall.sh` with clear preflight checks.
5. Add health check verification and optional warmup.
6. Add minimal test/verify tooling.
7. Validate on Pi and adjust defaults (memory/CPU) as needed.

---

## 14) Future improvements (post-v1)

- Add a reverse-proxy option (nginx/caddy) with optional TLS.
- Add systemd drop-in overrides instead of editing the unit directly.
- Add metrics (basic `/health` wrapper via a tiny sidecar) if needed.
- Add a “model allowlist” policy for kiosk/art-installation deployments.
- Improve contention behavior if multiple Hailo services compete (e.g., staggered start, backoff).

