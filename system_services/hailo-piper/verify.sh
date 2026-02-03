#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-piper"
DEFAULT_PORT="5002"

log() {
    echo "[verify] $*"
}

error() {
    echo "[verify] ERROR: $*" >&2
}

get_config_port() {
    /opt/hailo-piper/venv/bin/python3 - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
path = "/etc/hailo/hailo-piper.yaml"
try:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    port = data.get("server", {}).get("port", 5002)
    print(int(port))
except Exception:
    print(5002)
PY
}

verify_systemd_status() {
    log "Checking systemd service status..."
    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service is not active"
        systemctl status "${SERVICE_NAME}.service" --no-pager || true
        return 1
    fi
    log "✓ Service is active"
    return 0
}

verify_health_endpoint() {
    local port="$1"
    log "Checking health endpoint on port ${port}..."
    
    if ! command -v curl >/dev/null 2>&1; then
        error "curl not found; skipping health check"
        return 1
    fi
    
    local response
    if ! response=$(curl -fsS "http://localhost:${port}/health" 2>&1); then
        error "Health check failed"
        echo "Response: ${response}"
        return 1
    fi
    
    log "✓ Health endpoint responding"
    echo "${response}" | python3 -m json.tool 2>/dev/null || echo "${response}"
    return 0
}

verify_synthesis() {
    local port="$1"
    log "Testing speech synthesis..."
    
    local tmpfile="/tmp/hailo-piper-test-$$.wav"
    
    if ! curl -X POST "http://localhost:${port}/v1/audio/speech" \
        -H "Content-Type: application/json" \
        -d '{"input": "Testing Hailo Piper TTS service"}' \
        --output "${tmpfile}" \
        --silent --show-error --fail; then
        error "Synthesis test failed"
        rm -f "${tmpfile}"
        return 1
    fi
    
    # Check if file was created and has content
    if [[ ! -s "${tmpfile}" ]]; then
        error "Synthesis produced empty file"
        rm -f "${tmpfile}"
        return 1
    fi
    
    local filesize
    filesize=$(stat -c%s "${tmpfile}" 2>/dev/null || stat -f%z "${tmpfile}" 2>/dev/null)
    log "✓ Synthesis succeeded (${filesize} bytes)"
    
    # Check if it's a valid WAV file
    if command -v file >/dev/null 2>&1; then
        local filetype
        filetype=$(file -b "${tmpfile}")
        if [[ "${filetype}" == *"WAVE"* ]] || [[ "${filetype}" == *"WAV"* ]]; then
            log "✓ Valid WAV file: ${filetype}"
        else
            error "Output is not a WAV file: ${filetype}"
            rm -f "${tmpfile}"
            return 1
        fi
    fi
    
    rm -f "${tmpfile}"
    return 0
}

verify_logs() {
    log "Recent service logs:"
    journalctl -u "${SERVICE_NAME}.service" -n 10 --no-pager
}

main() {
    log "Verifying Hailo Piper TTS Service"
    log "=================================="
    
    local port
    port="$(get_config_port)"
    
    local failures=0
    
    verify_systemd_status || ((failures++))
    verify_health_endpoint "${port}" || ((failures++))
    verify_synthesis "${port}" || ((failures++))
    
    echo ""
    verify_logs
    echo ""
    
    if [[ ${failures} -eq 0 ]]; then
        log "All checks passed ✓"
        return 0
    else
        error "${failures} check(s) failed"
        return 1
    fi
}

main "$@"
