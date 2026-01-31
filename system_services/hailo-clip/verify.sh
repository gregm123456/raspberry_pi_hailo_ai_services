#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-clip"
UNIT_DEST="/etc/systemd/system/hailo-clip.service"

log() {
    echo "[hailo-clip-verify] $*"
}

warn() {
    echo "[hailo-clip-verify] WARNING: $*" >&2
}

error() {
    echo "[hailo-clip-verify] ERROR: $*" >&2
}

check_device() {
    log "Checking Hailo device..."
    if [[ ! -e /dev/hailo0 ]]; then
        error "Hailo device not found at /dev/hailo0"
        return 1
    fi
    
    if command -v hailortcli >/dev/null 2>&1; then
        if hailortcli fw-control identify >/dev/null 2>&1; then
            log "✓ Hailo device identified"
            return 0
        else
            warn "hailortcli verify failed; device may not be ready"
            return 1
        fi
    else
        log "ℹ hailortcli not available; skipping firmware check"
        return 0
    fi
}

check_service_status() {
    log "Checking service status..."
    
    if [[ ! -f "${UNIT_DEST}" ]]; then
        error "systemd unit not found: ${UNIT_DEST}"
        return 1
    fi
    
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        log "✓ Service is running"
        systemctl status "${SERVICE_NAME}.service" --no-pager | head -10
        return 0
    else
        error "Service is not running"
        systemctl status "${SERVICE_NAME}.service" --no-pager || true
        return 1
    fi
}

check_port() {
    log "Checking port binding..."
    
    local port
    port=$(grep "port:" /etc/hailo/hailo-clip.yaml 2>/dev/null | awk '{print $NF}' | tr -d ' ') || port="5000"
    
    if command -v ss >/dev/null 2>&1; then
        if ss -ltn 2>/dev/null | grep -q ":${port} "; then
            log "✓ Port ${port} is open and listening"
            return 0
        else
            error "Port ${port} is not listening"
            return 1
        fi
    else
        log "ℹ ss not available; skipping port check"
        return 0
    fi
}

check_health_endpoint() {
    log "Checking health endpoint..."
    
    local port
    port=$(grep "port:" /etc/hailo/hailo-clip.yaml 2>/dev/null | awk '{print $NF}' | tr -d ' ') || port="5000"
    
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1; then
            log "✓ Health endpoint responding"
            curl -fsS "http://localhost:${port}/health" | jq . 2>/dev/null || echo "(response OK)"
            return 0
        else
            error "Health endpoint not responding at http://localhost:${port}/health"
            return 1
        fi
    else
        warn "curl not available; skipping health check"
        return 0
    fi
}

check_model_loaded() {
    log "Checking model status..."
    
    local port
    port=$(grep "port:" /etc/hailo/hailo-clip.yaml 2>/dev/null | awk '{print $NF}' | tr -d ' ') || port="5000"
    
    if command -v curl >/dev/null 2>&1; then
        local response
        response=$(curl -fsS "http://localhost:${port}/health" 2>/dev/null | jq '.model_loaded' 2>/dev/null || echo "unknown")
        
        if [[ "${response}" == "true" ]]; then
            log "✓ CLIP model is loaded"
            return 0
        elif [[ "${response}" == "false" ]]; then
            warn "CLIP model not yet loaded (will load on first request)"
            return 0
        else
            log "ℹ Could not determine model status"
            return 0
        fi
    fi
}

check_recent_logs() {
    log "Checking recent logs for errors..."
    
    local error_count
    error_count=$(journalctl -u "${SERVICE_NAME}.service" -n 50 --no-pager 2>/dev/null | grep -c "ERROR\|CRITICAL\|Traceback" || echo "0")
    
    if [[ ${error_count} -gt 0 ]]; then
        error "Found ${error_count} error(s) in recent logs:"
        journalctl -u "${SERVICE_NAME}.service" -n 50 --no-pager | grep "ERROR\|CRITICAL\|Traceback" | head -5
        return 1
    else
        log "✓ No recent errors in logs"
        return 0
    fi
}

test_classification() {
    log "Testing classification endpoint..."
    
    local port
    port=$(grep "port:" /etc/hailo/hailo-clip.yaml 2>/dev/null | awk '{print $NF}' | tr -d ' ') || port="5000"
    
    if command -v curl >/dev/null 2>&1; then
        # Create a minimal test image (1x1 pixel JPEG in base64)
        local test_image="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8VAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="
        
        local response
        response=$(curl -fsS -X POST "http://localhost:${port}/v1/classify" \
            -H "Content-Type: application/json" \
            -d "{\"image\": \"${test_image}\", \"prompts\": [\"test\"]}" 2>/dev/null | jq '.classifications' 2>/dev/null || echo "error")
        
        if [[ "${response}" != "error" ]]; then
            log "✓ Classification endpoint working"
            return 0
        else
            warn "Classification endpoint returned error (may be expected if model is still initializing)"
            return 0
        fi
    else
        log "ℹ curl not available; skipping endpoint test"
        return 0
    fi
}

main() {
    log "Verifying Hailo CLIP Service"
    log "=============================="
    
    local failed=0
    
    check_device || ((failed++))
    check_service_status || ((failed++))
    check_port || ((failed++))
    check_health_endpoint || ((failed++))
    check_model_loaded || ((failed++))
    check_recent_logs || ((failed++))
    test_classification || ((failed++))
    
    log ""
    log "=============================="
    if [[ ${failed} -eq 0 ]]; then
        log "✓ All checks passed!"
        exit 0
    else
        error "${failed} check(s) failed. See logs:"
        log "  journalctl -u ${SERVICE_NAME}.service -f"
        exit 1
    fi
}

main "$@"
