#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-whisper"
CONFIG_PATH="/etc/hailo/hailo-whisper.yaml"
DEFAULT_PORT="11436"

log() {
    echo "[verify] $*"
}

error() {
    echo "[verify] ERROR: $*" >&2
}

get_config_port() {
    python3 - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
import sys

path = "/etc/hailo/hailo-whisper.yaml"
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    server = data.get("server", {}) if isinstance(data, dict) else {}
    port = server.get("port", 11436)
    print(int(port))
except Exception:
    print(11436)
PY
}

verify_systemd() {
    log "Checking systemd service status"
    
    if ! systemctl is-enabled "${SERVICE_NAME}.service" >/dev/null 2>&1; then
        error "Service not enabled"
        return 1
    fi
    
    if ! systemctl is-active "${SERVICE_NAME}.service" >/dev/null 2>&1; then
        error "Service not active"
        log "Check logs: sudo journalctl -u ${SERVICE_NAME}.service -n 50 --no-pager"
        return 1
    fi
    
    log "✓ Service is enabled and active"
}

verify_config() {
    log "Checking configuration files"
    
    if [[ ! -f "${CONFIG_PATH}" ]]; then
        error "Config not found at ${CONFIG_PATH}"
        return 1
    fi
    
    local json_config="/etc/xdg/hailo-whisper/hailo-whisper.json"
    if [[ ! -f "${json_config}" ]]; then
        error "JSON config not found at ${json_config}"
        return 1
    fi
    
    log "✓ Configuration files present"
}

verify_health() {
    local port
    port=$(get_config_port)
    
    log "Checking HTTP health endpoint on port ${port}"
    
    if ! command -v curl >/dev/null 2>&1; then
        error "curl not found; install with: sudo apt install curl"
        return 1
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/health" 2>&1); then
        error "Health check failed"
        log "Response: ${response}"
        return 1
    fi
    
    log "✓ Health endpoint responding"
    log "Response: ${response}"
}

verify_models() {
    local port
    port=$(get_config_port)
    
    log "Checking model availability"
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/v1/models" 2>&1); then
        error "Models endpoint failed"
        return 1
    fi
    
    log "✓ Models endpoint responding"
    log "Response: ${response}"
}

verify_permissions() {
    log "Checking file permissions"
    
    if [[ ! -d /var/lib/hailo-whisper ]]; then
        error "State directory missing: /var/lib/hailo-whisper"
        return 1
    fi
    
    local owner
    owner=$(stat -c '%U:%G' /var/lib/hailo-whisper)
    if [[ "${owner}" != "hailo-whisper:hailo-whisper" ]]; then
        error "Incorrect ownership on /var/lib/hailo-whisper (expected hailo-whisper:hailo-whisper, got ${owner})"
        return 1
    fi
    
    log "✓ Permissions configured correctly"
}

main() {
    log "Verifying hailo-whisper service installation"
    
    local failed=0
    
    verify_systemd || ((failed++))
    verify_config || ((failed++))
    verify_permissions || ((failed++))
    verify_health || ((failed++))
    verify_models || ((failed++))
    
    echo ""
    if [[ ${failed} -eq 0 ]]; then
        log "✓ All verification checks passed"
        exit 0
    else
        error "${failed} verification check(s) failed"
        exit 1
    fi
}

main "$@"
