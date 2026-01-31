#!/usr/bin/env bash
set -euo pipefail

# Hailo Face Recognition Service Verification Script

SERVICE_NAME="hailo-face"
API_HOST="localhost"
API_PORT="5002"
BASE_URL="http://${API_HOST}:${API_PORT}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

success() {
    echo -e "${GREEN}[✓]${NC} $*"
}

fail() {
    echo -e "${RED}[✗]${NC} $*"
}

check_systemd_status() {
    info "Checking systemd service status..."
    
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        success "Service is running"
        return 0
    else
        fail "Service is not running"
        echo "Check logs: sudo journalctl -u ${SERVICE_NAME} -n 50"
        return 1
    fi
}

check_health_endpoint() {
    info "Checking health endpoint..."
    
    local response
    response=$(curl -s -f "${BASE_URL}/health" 2>/dev/null) || {
        fail "Health endpoint unreachable"
        return 1
    }
    
    if echo "$response" | grep -q '"status":"healthy"'; then
        success "Health check passed"
        echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        return 0
    else
        fail "Health check failed"
        echo "$response"
        return 1
    fi
}

check_detect_endpoint() {
    info "Checking face detection endpoint..."
    
    # Create a simple test image (1x1 red pixel as minimal base64)
    local test_image="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    
    local response
    response=$(curl -s -f -X POST "${BASE_URL}/v1/detect" \
        -H "Content-Type: application/json" \
        -d "{\"image\":\"${test_image}\"}" 2>/dev/null) || {
        fail "Detect endpoint error"
        return 1
    }
    
    if echo "$response" | grep -q '"faces"'; then
        success "Detect endpoint functional"
        return 0
    else
        warn "Detect endpoint returned unexpected response"
        echo "$response"
        return 1
    fi
}

check_database_list() {
    info "Checking database list endpoint..."
    
    local response
    response=$(curl -s -f "${BASE_URL}/v1/database/list" 2>/dev/null) || {
        fail "Database list endpoint error"
        return 1
    }
    
    if echo "$response" | grep -q '"identities"'; then
        success "Database list endpoint functional"
        local count
        count=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "?")
        info "Database contains ${count} identities"
        return 0
    else
        fail "Database list endpoint failed"
        return 1
    fi
}

check_logs() {
    info "Recent service logs:"
    echo "----------------------------------------"
    sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager || warn "Could not fetch logs"
    echo "----------------------------------------"
}

main() {
    info "Verifying Hailo Face Recognition Service..."
    echo ""
    
    local failed=0
    
    check_systemd_status || ((failed++))
    echo ""
    
    sleep 1
    
    check_health_endpoint || ((failed++))
    echo ""
    
    check_detect_endpoint || ((failed++))
    echo ""
    
    check_database_list || ((failed++))
    echo ""
    
    check_logs
    echo ""
    
    if [[ $failed -eq 0 ]]; then
        success "All checks passed!"
        info "Service URL: ${BASE_URL}"
        info "API documentation: /home/gregm/raspberry_pi_hailo_ai_services/system_services/${SERVICE_NAME}/API_SPEC.md"
        return 0
    else
        fail "${failed} check(s) failed"
        return 1
    fi
}

main "$@"
