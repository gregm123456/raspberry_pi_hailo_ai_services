#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-scrfd"
DEFAULT_PORT="5001"

log() {
    echo "[hailo-scrfd] $*"
}

error() {
    echo "[hailo-scrfd] ERROR: $*" >&2
}

require_command() {
    local cmd="$1"
    local hint="$2"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        error "Missing required command: ${cmd}. ${hint}"
        return 1
    fi
    return 0
}

get_config_port() {
    python3 - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
import sys

path = "/etc/hailo/hailo-scrfd.yaml"
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    server = data.get("server", {}) if isinstance(data, dict) else {}
    port = server.get("port", 5001)
    print(int(port))
except Exception:
    print(5001)
PY
}

check_systemd_status() {
    log "Checking systemd status..."
    
    if ! systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        error "Service is not enabled"
        return 1
    fi
    
    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service is not running"
        systemctl status "${SERVICE_NAME}.service" --no-pager || true
        return 1
    fi
    
    log "✓ Service is enabled and running"
    return 0
}

check_health_endpoint() {
    local port="$1"
    log "Checking health endpoint on port ${port}..."
    
    if ! require_command curl "Install with: sudo apt install curl"; then
        return 1
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/health" 2>&1); then
        error "Health check failed: ${response}"
        return 1
    fi
    
    log "✓ Health endpoint responding: ${response}"
    return 0
}

check_detect_endpoint() {
    local port="$1"
    log "Checking face detection endpoint..."
    
    if ! require_command curl "Install with: sudo apt install curl"; then
        return 1
    fi
    
    # Create a simple test image (1x1 white pixel)
    local test_image="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    
    local response
    if ! response=$(curl -fsS -X POST "http://localhost:${port}/v1/detect" \
        -H "Content-Type: application/json" \
        -d "{\"image\": \"data:image/png;base64,${test_image}\", \"conf_threshold\": 0.5}" 2>&1); then
        error "Detection endpoint failed: ${response}"
        return 1
    fi
    
    log "✓ Detection endpoint responding"
    return 0
}

check_logs() {
    log "Checking recent logs..."
    
    local errors
    errors=$(journalctl -u "${SERVICE_NAME}.service" --since "5 minutes ago" --no-pager -p err 2>/dev/null || true)
    
    if [[ -n "${errors}" ]]; then
        error "Found errors in logs:"
        echo "${errors}"
        return 1
    fi
    
    log "✓ No errors in recent logs"
    return 0
}

check_config() {
    log "Checking configuration..."
    
    local config_path="/etc/hailo/hailo-scrfd.yaml"
    if [[ ! -f "${config_path}" ]]; then
        error "Config file not found: ${config_path}"
        return 1
    fi
    
    log "✓ Config file exists: ${config_path}"
    return 0
}

check_hailo_device() {
    log "Checking Hailo device..."
    
    if [[ ! -e /dev/hailo0 ]]; then
        error "/dev/hailo0 not found"
        return 1
    fi
    
    log "✓ Hailo device present: /dev/hailo0"
    return 0
}

main() {
    log "Starting verification for ${SERVICE_NAME} service"
    log "================================================"
    
    local exit_code=0
    
    check_hailo_device || exit_code=1
    check_config || exit_code=1
    check_systemd_status || exit_code=1
    
    local port
    port="$(get_config_port)"
    log "Using port: ${port}"
    
    check_health_endpoint "${port}" || exit_code=1
    check_detect_endpoint "${port}" || exit_code=1
    check_logs || exit_code=1
    
    log "================================================"
    if [[ ${exit_code} -eq 0 ]]; then
        log "✓ All checks passed"
    else
        error "Some checks failed. Review output above."
    fi
    
    exit ${exit_code}
}

main "$@"
