#!/bin/bash
# hailo-florence Service Verification Script
# Tests service health, API functionality, and model performance

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICE_NAME="hailo-florence"
API_BASE="http://localhost:11438"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0

log_test() {
    echo -e "${YELLOW}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

# Test 1: Service Status
test_service_status() {
    log_test "Checking systemd service status..."
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_pass "Service is running"
        return 0
    else
        log_fail "Service is not running"
        echo "Run: sudo systemctl status $SERVICE_NAME"
        return 1
    fi
}

# Test 2: Health Endpoint
test_health_endpoint() {
    log_test "Testing health endpoint..."
    
    response=$(curl -s -w "\n%{http_code}" "$API_BASE/health" 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        log_pass "Health endpoint returned 200 OK"
        
        # Parse JSON response
        if echo "$body" | grep -q '"status"'; then
            status=$(echo "$body" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            model_loaded=$(echo "$body" | grep -o '"model_loaded":[^,}]*' | cut -d':' -f2)
            
            log_info "Status: $status"
            log_info "Model loaded: $model_loaded"
            
            if [ "$model_loaded" = "true" ]; then
                log_pass "Model is loaded and ready"
            else
                log_fail "Model is not loaded"
            fi
        fi
        return 0
    else
        log_fail "Health endpoint returned $http_code (expected 200)"
        return 1
    fi
}

# Test 3: Hailo Device Access
test_hailo_device() {
    log_test "Checking Hailo device accessibility..."
    
    if command -v hailortcli &> /dev/null; then
        if hailortcli fw-control identify &> /dev/null; then
            device_info=$(hailortcli fw-control identify | grep 'Device Architecture' | awk '{print $3}')
            log_pass "Hailo device accessible: $device_info"
            return 0
        else
            log_fail "Hailo device not responding"
            return 1
        fi
    else
        log_fail "hailortcli not found"
        return 1
    fi
}

# Test 4: Caption Generation (with test image)
test_caption_generation() {
    log_test "Testing caption generation..."
    
    # Create a simple test image (1x1 red pixel)
    test_image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    
    # Make API request
    response=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/v1/caption" \
        -H "Content-Type: application/json" \
        -d "{\"image\": \"data:image/png;base64,$test_image_b64\", \"max_length\": 50}" \
        2>/dev/null || echo "000")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        log_pass "Caption API returned 200 OK"
        
        # Parse response
        if echo "$body" | grep -q '"caption"'; then
            caption=$(echo "$body" | grep -o '"caption":"[^"]*"' | cut -d'"' -f4)
            inference_time=$(echo "$body" | grep -o '"inference_time_ms":[0-9]*' | cut -d':' -f2)
            
            log_info "Caption: $caption"
            log_info "Inference time: ${inference_time}ms"
            
            if [ -n "$caption" ]; then
                log_pass "Caption generated successfully"
                return 0
            else
                log_fail "Caption is empty"
                return 1
            fi
        else
            log_fail "Response missing caption field"
            echo "Body: $body"
            return 1
        fi
    elif [ "$http_code" = "503" ]; then
        log_fail "Service unavailable (model may still be loading)"
        log_info "Wait a minute and try again, or check logs:"
        log_info "  sudo journalctl -u $SERVICE_NAME -n 50"
        return 1
    else
        log_fail "Caption API returned $http_code (expected 200)"
        echo "Body: $body"
        return 1
    fi
}

# Test 5: VQA Endpoint
test_vqa_endpoint() {
    log_test "Testing VQA endpoint..."

    test_image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

    response=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/v1/vqa" \
        -H "Content-Type: application/json" \
        -d "{\"image\": \"data:image/png;base64,$test_image_b64\", \"question\": \"What is shown?\"}" \
        2>/dev/null || echo "000")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        log_pass "VQA API returned 200 OK"
        return 0
    elif [ "$http_code" = "501" ]; then
        log_warn "VQA not configured (missing VQA embedding)."
        return 0
    else
        log_fail "VQA API returned $http_code (expected 200 or 501)"
        echo "Body: $body"
        return 1
    fi
}

# Test 6: Metrics Endpoint
test_metrics_endpoint() {
    log_test "Testing metrics endpoint..."
    
    response=$(curl -s -w "\n%{http_code}" "$API_BASE/metrics" 2>/dev/null || echo "000")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        log_pass "Metrics endpoint returned 200 OK"
        
        # Check for expected fields
        if echo "$body" | grep -q '"requests_total"'; then
            requests_total=$(echo "$body" | grep -o '"requests_total":[0-9]*' | cut -d':' -f2)
            log_info "Total requests: $requests_total"
            log_pass "Metrics data available"
        fi
        return 0
    else
        log_fail "Metrics endpoint returned $http_code (expected 200)"
        return 1
    fi
}

# Test 7: Service Logs
test_service_logs() {
    log_test "Checking service logs for errors..."
    
    if ! command -v journalctl &> /dev/null; then
        log_fail "journalctl not available"
        return 1
    fi
    
    # Check for recent error messages
    error_count=$(journalctl -u "$SERVICE_NAME" --since "5 minutes ago" -p err --no-pager 2>/dev/null | wc -l)
    
    if [ "$error_count" -eq 0 ]; then
        log_pass "No errors in recent logs"
        return 0
    else
        log_fail "Found $error_count error(s) in logs"
        log_info "View logs: sudo journalctl -u $SERVICE_NAME -n 50"
        return 1
    fi
}

# Test 8: Memory Usage
test_memory_usage() {
    log_test "Checking memory usage..."
    
    if ! command -v systemctl &> /dev/null; then
        log_fail "systemctl not available"
        return 1
    fi
    
    # Get memory usage from systemd
    memory_usage=$(systemctl show "$SERVICE_NAME" --property=MemoryCurrent | cut -d'=' -f2)
    
    if [ "$memory_usage" != "[not set]" ] && [ -n "$memory_usage" ]; then
        memory_mb=$((memory_usage / 1024 / 1024))
        log_info "Memory usage: ${memory_mb} MB"
        
        if [ "$memory_mb" -lt 3072 ]; then
            log_pass "Memory usage within limits (< 3GB)"
            return 0
        else
            log_fail "Memory usage exceeds 3GB limit"
            return 1
        fi
    else
        log_fail "Cannot determine memory usage"
        return 1
    fi
}

# Run all tests
run_tests() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "hailo-florence Service Verification"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    test_service_status || true
    echo ""
    
    test_hailo_device || true
    echo ""
    
    test_health_endpoint || true
    echo ""
    
    test_caption_generation || true
    echo ""
    
    test_vqa_endpoint || true
    echo ""

    test_metrics_endpoint || true
    echo ""
    
    test_service_logs || true
    echo ""
    
    test_memory_usage || true
    echo ""
    
    # Summary
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
    echo -e "${RED}Failed:${NC} $TESTS_FAILED"
    echo ""
    
    if [ "$TESTS_FAILED" -eq 0 ]; then
        log_pass "All tests passed! ✓"
        echo ""
        log_info "Service is healthy and ready for use"
        log_info "API Endpoint: $API_BASE/v1/caption"
        return 0
    else
        log_fail "Some tests failed"
        echo ""
        log_info "Troubleshooting:"
        log_info "  1. Check service status: sudo systemctl status $SERVICE_NAME"
        log_info "  2. View logs: sudo journalctl -u $SERVICE_NAME -f"
        log_info "  3. See TROUBLESHOOTING.md for common issues"
        return 1
    fi
}

# Main
main() {
    run_tests
}

main "$@"
