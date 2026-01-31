#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-ocr"
PORT="11436"

log() {
    echo "[hailo-ocr-verify] $*"
}

error() {
    echo "[hailo-ocr-verify] ERROR: $*" >&2
}

check_service_running() {
    log "Checking if service is running..."
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        log "✓ Service is running"
        return 0
    else
        error "Service is not running"
        log "Start with: sudo systemctl start ${SERVICE_NAME}.service"
        return 1
    fi
}

check_health_endpoint() {
    log "Checking health endpoint..."
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS "http://localhost:${PORT}/health" >/dev/null 2>&1; then
            log "✓ Health check passed"
            
            # Get full health info
            local health_json
            health_json=$(curl -s "http://localhost:${PORT}/health")
            log "Details: $health_json"
            return 0
        else
            error "Health check failed"
            log "Check logs: sudo journalctl -u ${SERVICE_NAME}.service -n 20 --no-pager"
            return 1
        fi
    else
        error "curl not found; skipping health check"
        return 1
    fi
}

check_models_endpoint() {
    log "Checking models endpoint..."
    if command -v curl >/dev/null 2>&1; then
        local models_json
        models_json=$(curl -s "http://localhost:${PORT}/models" 2>/dev/null || echo "")
        if [[ -n "$models_json" ]]; then
            log "✓ Models endpoint working"
            log "Available models: $models_json" | head -c 200
            return 0
        else
            error "Models endpoint failed"
            return 1
        fi
    else
        return 1
    fi
}

check_ocr_extract() {
    log "Testing simple OCR extraction..."
    
    if ! command -v python3 >/dev/null 2>&1; then
        error "python3 not found"
        return 1
    fi
    
    python3 << 'PY'
import base64
import json
import urllib.request
from PIL import Image, ImageDraw
import io

# Create test image
img = Image.new('RGB', (200, 100), color='white')
d = ImageDraw.Draw(img)
d.text((40, 40), "HAILO OCR", fill='black')

# Convert to JPEG bytes
img_bytes = io.BytesIO()
img.save(img_bytes, format='JPEG')
img_bytes_data = img_bytes.getvalue()

# Base64 encode
b64 = base64.b64encode(img_bytes_data).decode()

# Send to OCR service
payload = {
    "image": f"data:image/jpeg;base64,{b64}",
    "languages": ["en"]
}

try:
    req = urllib.request.Request(
        "http://localhost:11436/v1/ocr/extract",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode())
        
        if result.get('success'):
            print(f"✓ OCR test passed. Text: {result.get('text', 'N/A')}")
            exit(0)
        else:
            print(f"✗ OCR failed: {result.get('error', 'Unknown error')}")
            exit(1)
except urllib.error.URLError as e:
    print(f"✗ Connection error: {e}")
    exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)
PY
}

check_config() {
    log "Checking configuration..."
    local config_file="/etc/hailo/hailo-ocr.yaml"
    
    if [[ -f "$config_file" ]]; then
        log "✓ Config file exists: $config_file"
        
        # Validate with render script
        if python3 "${SCRIPT_DIR}/render_config.py" --input "$config_file" --validate-only 2>/dev/null; then
            log "✓ Config is valid"
            return 0
        else
            error "Config validation failed"
            return 1
        fi
    else
        error "Config file not found: $config_file"
        return 1
    fi
}

check_logs() {
    log "Recent service logs:"
    if command -v journalctl >/dev/null 2>&1; then
        journalctl -u "${SERVICE_NAME}.service" -n 10 --no-pager | sed 's/^/  /'
    fi
}

main() {
    local SCRIPT_DIR
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    log "========================================"
    log "Hailo OCR Service Verification"
    log "========================================"
    
    local failed=0
    
    check_service_running || failed=$((failed + 1))
    check_health_endpoint || failed=$((failed + 1))
    check_models_endpoint || failed=$((failed + 1))
    check_ocr_extract || failed=$((failed + 1))
    check_config || failed=$((failed + 1))
    
    echo ""
    check_logs
    
    echo ""
    if [[ $failed -eq 0 ]]; then
        log "✓ All checks passed!"
        exit 0
    else
        log "✗ $failed check(s) failed"
        log "View full logs: sudo journalctl -u ${SERVICE_NAME}.service -f"
        exit 1
    fi
}

main "$@"
