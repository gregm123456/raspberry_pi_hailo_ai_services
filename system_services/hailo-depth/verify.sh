#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-depth"
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
path = "/etc/hailo/hailo-depth.yaml"
try:
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    port = data.get("server", {}).get("port", 11436)
    print(int(port))
except Exception:
    print(11436)
PY
}

verify_systemd() {
    log "Checking systemd service status..."
    
    if ! systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        error "Service is not enabled"
        return 1
    fi
    
    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service is not running"
        log "Check logs: journalctl -u ${SERVICE_NAME}.service -n 50"
        return 1
    fi
    
    log "✓ Service is enabled and running"
    return 0
}

verify_health() {
    local port="$1"
    log "Checking health endpoint at http://localhost:${port}/health..."
    
    if ! command -v curl >/dev/null 2>&1; then
        error "curl not found, cannot verify HTTP endpoint"
        return 1
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/health" 2>&1); then
        error "Health check failed: ${response}"
        return 1
    fi
    
    log "✓ Health check passed"
    echo "${response}" | python3 -m json.tool 2>/dev/null || echo "${response}"
    return 0
}

verify_api() {
    local port="$1"
    log "Checking API info endpoint..."
    
    if ! command -v curl >/dev/null 2>&1; then
        return 0  # Skip if curl not available
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/v1/info" 2>&1); then
        error "API info check failed: ${response}"
        return 1
    fi
    
    log "✓ API info endpoint responds"
    echo "${response}" | python3 -m json.tool 2>/dev/null || echo "${response}"
    return 0
}

verify_logs() {
    log "Checking recent logs..."
    journalctl -u "${SERVICE_NAME}.service" -n 10 --no-pager | tail -5
    return 0
}

main() {
    local port
    port="$(get_config_port)"
    
    log "Verifying hailo-depth service (port: ${port})"
    echo ""
    
    local failed=0
    
    verify_systemd || failed=1
    echo ""
    
    verify_health "${port}" || failed=1
    echo ""
    
    verify_api "${port}" || failed=1
    echo ""
    
    verify_logs
    echo ""
    
    if [[ ${failed} -eq 0 ]]; then
        log "All checks passed ✓"
        return 0
    else
        error "Some checks failed"
        return 1
    fi
}

main "$@"
