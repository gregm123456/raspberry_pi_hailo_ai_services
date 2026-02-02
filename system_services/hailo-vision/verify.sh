#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-vision"
DEFAULT_PORT="11435"

log() {
    echo "[hailo-vision-verify] $*"
}

error() {
    echo "[hailo-vision-verify] ERROR: $*" >&2
}

check_device() {
    log "Checking Hailo device..."
    if [[ ! -e /dev/hailo0 ]]; then
        error "Device /dev/hailo0 not found"
        return 1
    fi
    log "✓ Device /dev/hailo0 present"

    if command -v hailortcli >/dev/null 2>&1; then
        if hailortcli fw-control identify >/dev/null 2>&1; then
            log "✓ Hailo firmware OK"
        else
            error "Hailo firmware verification failed"
            return 1
        fi
    else
        log "✓ hailortcli not available (skipping firmware check)"
    fi
}

check_user_group() {
    log "Checking user and group..."
    if id "${SERVICE_NAME}" >/dev/null 2>&1; then
        log "✓ System user ${SERVICE_NAME} exists"
    else
        error "System user ${SERVICE_NAME} not found"
        return 1
    fi

    if getent group "${SERVICE_NAME}" >/dev/null; then
        log "✓ System group ${SERVICE_NAME} exists"
    else
        error "System group ${SERVICE_NAME} not found"
        return 1
    fi
}

check_directories() {
    log "Checking directories..."
    local dirs=(
        /var/lib/hailo-vision
        /var/lib/hailo-vision/resources
        /var/lib/hailo-vision/resources/models
        /etc/xdg/hailo-vision
    )
    for dir in "${dirs[@]}"; do
        if [[ -d "${dir}" ]]; then
            log "✓ ${dir} exists"
        else
            error "Directory not found: ${dir}"
            return 1
        fi
    done
}

check_config() {
    log "Checking configuration..."
    if [[ -f /etc/hailo/hailo-vision.yaml ]]; then
        log "✓ Config file exists: /etc/hailo/hailo-vision.yaml"
    else
        error "Config file not found: /etc/hailo/hailo-vision.yaml"
        return 1
    fi

    if [[ -f /etc/xdg/hailo-vision/hailo-vision.json ]]; then
        log "✓ JSON config exists: /etc/xdg/hailo-vision/hailo-vision.json"
    else
        error "JSON config not found: /etc/xdg/hailo-vision/hailo-vision.json"
        return 1
    fi
}

check_service() {
    log "Checking systemd service..."
    if [[ -f /etc/systemd/system/hailo-vision.service ]]; then
        log "✓ Service unit found"
    else
        error "Service unit not found: /etc/systemd/system/hailo-vision.service"
        return 1
    fi

    if systemctl is-enabled hailo-vision.service >/dev/null 2>&1; then
        log "✓ Service is enabled"
    else
        error "Service is not enabled"
        return 1
    fi
}

check_service_status() {
    log "Checking service runtime status..."
    if systemctl is-active --quiet hailo-vision.service; then
        log "✓ Service is running"
        systemctl status hailo-vision.service --no-pager | head -n 5
    else
        error "Service is not running"
        log "Start with: sudo systemctl start hailo-vision.service"
        return 1
    fi
}

check_health() {
    log "Checking health endpoint..."
    local port="${DEFAULT_PORT}"

    if command -v curl >/dev/null 2>&1; then
        if curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1; then
            log "✓ Health endpoint responding"
            curl -s "http://localhost:${port}/health" | python3 -m json.tool 2>/dev/null || log "Health response (unparseable)"
        else
            error "Health endpoint not responding (service may still be loading)"
            log "Try again in a few seconds, or check logs: sudo journalctl -u hailo-vision.service -f"
            return 1
        fi
    else
        log "⊘ curl not available; skipping health check"
    fi
}

check_ports() {
    log "Checking ports..."
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -q "hailo-vision"; then
            log "✓ Service port is bound"
        else
            log "✓ Port check (service may still be loading)"
        fi
    else
        log "⊘ ss not available; skipping port check"
    fi
}

check_logs() {
    log "Recent service logs (last 10 lines):"
    if command -v journalctl >/dev/null 2>&1; then
        sudo journalctl -u hailo-vision.service -n 10 --no-pager | sed 's/^/  /'
    else
        log "journalctl not available"
    fi
}

main() {
    log "=== Hailo Vision Service Verification ==="
    log ""

    local failed=0

    check_device || failed=$((failed + 1))
    log ""

    check_user_group || failed=$((failed + 1))
    log ""

    check_directories || failed=$((failed + 1))
    log ""

    check_config || failed=$((failed + 1))
    log ""

    check_service || failed=$((failed + 1))
    log ""

    check_service_status || failed=$((failed + 1))
    log ""

    check_health || failed=$((failed + 1))
    log ""

    check_ports
    log ""

    check_logs
    log ""

    if [[ ${failed} -eq 0 ]]; then
        log "=== ✓ All checks passed ==="
        exit 0
    else
        error "=== ✗ ${failed} check(s) failed ==="
        exit 1
    fi
}

main "$@"
