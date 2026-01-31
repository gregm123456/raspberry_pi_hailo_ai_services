#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-ocr"
SERVICE_USER="hailo-ocr"
SERVICE_GROUP="hailo-ocr"
UNIT_SRC="${SCRIPT_DIR}/hailo-ocr.service"
UNIT_DEST="/etc/systemd/system/hailo-ocr.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-ocr.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-ocr"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-ocr.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="11436"
SERVER_SCRIPT="${SCRIPT_DIR}/hailo_ocr_server.py"
INSTALL_TARGET="/usr/local/bin/hailo-ocr-server"

WARMUP_MODELS=""

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --warmup-models    Download and cache models after install (optional)
  -h, --help         Show this help
EOF
}

log() {
    echo "[hailo-ocr] $*"
}

warn() {
    echo "[hailo-ocr] WARNING: $*" >&2
}

error() {
    echo "[hailo-ocr] ERROR: $*" >&2
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "This script must be run as root (use: sudo ./install.sh)"
        exit 1
    fi
}

require_command() {
    local cmd="$1"
    local hint="$2"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        error "Missing required command: ${cmd}. ${hint}"
        exit 1
    fi
}

check_python_deps() {
    require_command python3 "Install with: sudo apt install python3"
    
    if ! python3 - <<'PY' >/dev/null 2>&1
import sys
try:
    import yaml
    import PIL
    import aiohttp
    print("OK")
except ImportError as e:
    raise
PY
    then
        error "Required Python packages missing."
        error ""
        error "Install dependencies with:"
        error "  sudo apt install python3-yaml python3-pil"
        error "  pip3 install aiohttp paddleocr"
        error ""
        error "Or all at once:"
        error "  sudo apt install python3-yaml python3-pil && pip3 install aiohttp paddleocr"
        exit 1
    fi
}

create_user_group() {
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Creating system group ${SERVICE_GROUP}"
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Creating system user ${SERVICE_USER}"
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-ocr -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
}

create_state_directories() {
    log "Creating service directory structure"
    mkdir -p /var/lib/hailo-ocr/models
    mkdir -p /var/lib/hailo-ocr/cache
    mkdir -p /var/lib/hailo-ocr/temp

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-ocr
    chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-ocr
}

install_config() {
    install -d -m 0755 /etc/hailo
    if [[ ! -f "${ETC_HAILO_CONFIG}" ]]; then
        log "Installing default config to ${ETC_HAILO_CONFIG}"
        install -m 0644 "${CONFIG_TEMPLATE}" "${ETC_HAILO_CONFIG}"
    else
        log "Config already exists at ${ETC_HAILO_CONFIG} (leaving unchanged)"
    fi

    install -d -m 0755 "${ETC_XDG_DIR}"
    log "Rendering JSON config to ${JSON_CONFIG}"
    python3 "${RENDER_SCRIPT}" --input "${ETC_HAILO_CONFIG}" --output "${JSON_CONFIG}"
}

install_server_script() {
    if [[ ! -f "${SERVER_SCRIPT}" ]]; then
        error "Server script not found: ${SERVER_SCRIPT}"
        exit 1
    fi

    log "Installing server script to ${INSTALL_TARGET}"
    install -m 0755 "${SERVER_SCRIPT}" "${INSTALL_TARGET}"
}

get_config_port() {
    python3 - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
import sys

path = "/etc/hailo/hailo-ocr.yaml"
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

warn_if_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-ocr.yaml if needed."
        fi
    fi
}

install_unit() {
    log "Installing systemd unit to ${UNIT_DEST}"
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"

    systemctl daemon-reload
    systemctl enable --now "${SERVICE_NAME}.service"
}

verify_service() {
    local port="$1"

    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service failed to start. Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
        return 1
    fi

    if command -v curl >/dev/null 2>&1; then
        local attempt
        for attempt in {1..10}; do
            if curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1; then
                log "Health check succeeded on port ${port}"
                return 0
            fi
            sleep 1
        done
        warn "Health check failed at http://localhost:${port}/health"
        warn "Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
    else
        warn "curl not found; skipping HTTP health check"
    fi
}

warmup_models() {
    local port="$1"
    log "Warmup: downloading and caching models (this may take 2-5 minutes)..."
    sleep 3  # Give service time to initialize
    
    # Create a small test image
    python3 << 'PY'
from PIL import Image, ImageDraw
import base64
import json
import urllib.request

img = Image.new('RGB', (200, 100), color='white')
d = ImageDraw.Draw(img)
d.text((50, 40), "TEST", fill='black')

# Save to bytes
import io
img_bytes = io.BytesIO()
img.save(img_bytes, format='JPEG')
img_bytes = img_bytes.getvalue()

# Encode as base64
b64 = base64.b64encode(img_bytes).decode()

# Send to OCR service
payload = {
    "image": f"data:image/jpeg;base64,{b64}",
    "languages": ["en"]
}

try:
    req = urllib.request.Request(
        "http://localhost:11436/v1/ocr/extract",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        print("Warmup complete")
except Exception as e:
    print(f"Warmup failed: {e}")
PY
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --warmup-models)
                WARMUP_MODELS="true"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

main() {
    parse_args "$@"
    require_root
    check_python_deps

    log "Installing ${SERVICE_NAME} service..."

    create_user_group
    create_state_directories
    install_config
    install_server_script

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    if [[ -n "${WARMUP_MODELS}" ]]; then
        warmup_models "${port}" || warn "Warmup failed; models will load on first request"
    fi

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
    log "Start service: sudo systemctl start ${SERVICE_NAME}.service"
    log "View logs: sudo journalctl -u ${SERVICE_NAME}.service -f"
}

main "$@"
