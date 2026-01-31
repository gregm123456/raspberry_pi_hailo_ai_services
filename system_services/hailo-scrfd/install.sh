#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-scrfd"
SERVICE_USER="hailo-scrfd"
SERVICE_GROUP="hailo-scrfd"
UNIT_SRC="${SCRIPT_DIR}/hailo-scrfd.service"
UNIT_DEST="/etc/systemd/system/hailo-scrfd.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-scrfd.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-scrfd"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-scrfd.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="5001"
SERVICE_DIR="/opt/hailo-scrfd"

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --warmup    Pre-load SCRFD model and run warmup inference
  -h, --help  Show this help
EOF
}

log() {
    echo "[hailo-scrfd] $*"
}

warn() {
    echo "[hailo-scrfd] WARNING: $*" >&2
}

error() {
    echo "[hailo-scrfd] ERROR: $*" >&2
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

check_python_requirements() {
    require_command python3 "Install with: sudo apt install python3"
    if ! python3 - <<'PY' >/dev/null 2>&1
import yaml
import numpy
import PIL
import cv2
import flask
PY
    then
        error "Missing required Python packages. Install with:"
        error "  sudo apt install python3-yaml python3-numpy python3-pil python3-flask"
        error "  pip3 install opencv-python"
        exit 1
    fi
}

preflight_hailo() {
    if [[ ! -e /dev/hailo0 ]]; then
        error "/dev/hailo0 not found. Install Hailo driver: sudo apt install dkms hailo-h10-all"
        exit 1
    fi

    if command -v hailortcli >/dev/null 2>&1; then
        if ! hailortcli fw-control identify >/dev/null 2>&1; then
            warn "hailortcli verification failed. Hailo device may not be ready."
        fi
    else
        warn "hailortcli not found; skipping firmware verification."
    fi
}

preflight_scrfd_models() {
    # Check if hailo-apps postprocessing is available
    local hailo_apps_path="${SCRIPT_DIR}/../../../hailo-apps"
    if [[ ! -d "${hailo_apps_path}/hailo_apps/postprocess" ]]; then
        error "SCRFD postprocessing not found in hailo-apps. Ensure hailo-apps submodule is initialized."
        exit 1
    fi
    
    log "Found hailo-apps postprocessing at ${hailo_apps_path}"
}

create_user_group() {
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Creating system group ${SERVICE_GROUP}"
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Creating system user ${SERVICE_USER}"
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-scrfd -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
}

configure_device_permissions() {
    local device_group
    device_group=$(stat -c '%G' /dev/hailo0)

    if [[ -z "${device_group}" ]]; then
        error "Could not determine group for /dev/hailo0"
        exit 1
    fi

    if ! getent group "${device_group}" >/dev/null; then
        error "Device group '${device_group}' not found. Check Hailo installation/udev rules."
        exit 1
    fi

    log "Adding ${SERVICE_USER} to ${device_group} group"
    usermod -aG "${device_group}" "${SERVICE_USER}"
}

create_state_directories() {
    log "Creating service directories"
    mkdir -p /var/lib/hailo-scrfd/{models,cache}
    mkdir -p "${SERVICE_DIR}"

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-scrfd
    chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-scrfd

    # Copy service code
    if [[ -f "${SCRIPT_DIR}/hailo_scrfd_service.py" ]]; then
        cp "${SCRIPT_DIR}/hailo_scrfd_service.py" "${SERVICE_DIR}/"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/hailo_scrfd_service.py"
        chmod 0755 "${SERVICE_DIR}/hailo_scrfd_service.py"
    fi
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

warn_if_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-scrfd.yaml if needed."
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
        warn "Service may still be initializing. Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
    else
        warn "curl not found; skipping HTTP health check"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --warmup)
                WARMUP="true"
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
    local WARMUP="false"
    parse_args "$@"

    require_root
    preflight_hailo
    preflight_scrfd_models
    check_python_requirements

    create_user_group
    configure_device_permissions
    create_state_directories
    install_config

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
    log "Service: systemctl status hailo-scrfd.service"
    log "Logs: journalctl -u hailo-scrfd.service -f"
}

main "$@"
