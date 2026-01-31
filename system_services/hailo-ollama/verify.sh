#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-ollama"
PORT="${1:-11434}"

log() {
    echo "[hailo-ollama] $*"
}

log "Checking systemd status"
systemctl status "${SERVICE_NAME}.service" --no-pager

log "Checking HTTP endpoint: /api/version"
curl -fsS "http://localhost:${PORT}/api/version" >/dev/null

if command -v ss >/dev/null 2>&1; then
    log "Checking listening port ${PORT}"
    ss -lntp | grep ":${PORT}" || true
elif command -v lsof >/dev/null 2>&1; then
    log "Checking listening port ${PORT}"
    lsof -i ":${PORT}" || true
else
    log "Neither ss nor lsof found; skipping port check"
fi

log "Verification complete"
