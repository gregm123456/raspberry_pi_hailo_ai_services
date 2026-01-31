#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-pose"
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

path = "/etc/hailo/hailo-pose.yaml"
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

check_systemd_status() {
    log "Checking systemd service status"
    
    if ! systemctl is-enabled --quiet "${SERVICE_NAME}.service"; then
        error "Service is not enabled"
        return 1
    fi
    
    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service is not active"
        systemctl status "${SERVICE_NAME}.service" --no-pager || true
        return 1
    fi
    
    log "✓ Service is enabled and active"
    return 0
}

check_health_endpoint() {
    local port="$1"
    log "Checking health endpoint at http://localhost:${port}/health"
    
    if ! command -v curl >/dev/null 2>&1; then
        error "curl not found, cannot verify health endpoint"
        return 1
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/health" 2>&1); then
        error "Health check failed: ${response}"
        return 1
    fi
    
    log "✓ Health endpoint responded: ${response}"
    return 0
}

check_readiness() {
    local port="$1"
    log "Checking readiness endpoint"
    
    if ! command -v curl >/dev/null 2>&1; then
        error "curl not found, cannot verify readiness"
        return 1
    fi
    
    local response status_code
    if ! response=$(curl -fsS "http://localhost:${port}/health/ready" 2>&1); then
        error "Readiness check failed: ${response}"
        return 1
    fi
    
    log "✓ Service is ready"
    return 0
}

check_models_endpoint() {
    local port="$1"
    log "Checking models endpoint"
    
    if ! command -v curl >/dev/null 2>&1; then
        return 0
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/v1/models" 2>&1); then
        error "Models endpoint failed: ${response}"
        return 1
    fi
    
    log "✓ Models endpoint responded"
    return 0
}

show_logs() {
    log "Recent service logs:"
    journalctl -u "${SERVICE_NAME}.service" -n 20 --no-pager || true
}

main() {
    local port
    port="$(get_config_port)"
    
    log "Verifying ${SERVICE_NAME} service on port ${port}"
    echo
    
    local failed=0
    
    check_systemd_status || failed=1
    check_health_endpoint "${port}" || failed=1
    check_readiness "${port}" || failed=1
    check_models_endpoint "${port}" || failed=1
    
    echo
    if [[ ${failed} -eq 0 ]]; then
        log "✓ All checks passed"
        return 0
    else
        error "Some checks failed"
        echo
        show_logs
        return 1
    fi
}

main "$@"
