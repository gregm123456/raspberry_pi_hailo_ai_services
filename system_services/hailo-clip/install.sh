#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-clip"
SERVICE_USER="hailo-clip"
SERVICE_GROUP="hailo-clip"
UNIT_SRC="${SCRIPT_DIR}/hailo-clip.service"
UNIT_DEST="/etc/systemd/system/hailo-clip.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-clip.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-clip"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-clip.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="5000"
SERVICE_DIR="/opt/hailo-clip"
DEVICE_MANAGER_CLIENT_SRC="${SCRIPT_DIR}/../../device_manager/device_client.py"
HAILO_APPS_SRC="${SCRIPT_DIR}/../../hailo-apps"
HAILO_APPS_VENDOR_DIR="${SERVICE_DIR}/vendor"
HAILO_APPS_VENDOR_PATH="${HAILO_APPS_VENDOR_DIR}/hailo-apps"

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --warmup    Pre-load CLIP model and run warmup inference
  -h, --help  Show this help
EOF
}

log() {
    echo "[hailo-clip] $*"
}

warn() {
    echo "[hailo-clip] WARNING: $*" >&2
}

error() {
    echo "[hailo-clip] ERROR: $*" >&2
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
import torch
import cv2
PY
    then
        error "Missing required Python packages. Install with:"
        error "  sudo apt install python3-yaml python3-numpy python3-pil python3-torch"
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

preflight_clip_models() {
    if [[ ! -d "${HAILO_APPS_SRC}/hailo_apps/python/pipeline_apps/clip" ]]; then
        error "CLIP application not found in hailo-apps. Ensure hailo-apps submodule is initialized."
        exit 1
    fi
}

vendor_hailo_apps() {
    log "Vendoring hailo-apps into ${HAILO_APPS_VENDOR_PATH}"
    rm -rf "${HAILO_APPS_VENDOR_PATH}"
    mkdir -p "${HAILO_APPS_VENDOR_DIR}"

    # Copy the hailo-apps repo into /opt so the systemd service user doesn't need
    # access to a developer home directory (e.g., /home/gregm).
    cp -a "${HAILO_APPS_SRC}" "${HAILO_APPS_VENDOR_DIR}/"

    # Ensure readable by the service user
    chown -R root:root "${HAILO_APPS_VENDOR_PATH}"
    chmod -R u+rwX,go+rX,go-w "${HAILO_APPS_VENDOR_PATH}"
}

create_user_group() {
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Creating system group ${SERVICE_GROUP}"
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Creating system user ${SERVICE_USER}"
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-clip -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
}

create_venv() {
    log "Creating Python virtual environment with system site packages"
    rm -rf "${SERVICE_DIR}/venv"
    python3 -m venv --system-site-packages "${SERVICE_DIR}/venv"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/venv"
}

install_requirements() {
    log "Installing Python requirements in venv"
    "${SERVICE_DIR}/venv/bin/pip" install --upgrade pip
    "${SERVICE_DIR}/venv/bin/pip" install -r "${SERVICE_DIR}/requirements.txt"

    log "Installing vendored hailo-apps into venv"
    "${SERVICE_DIR}/venv/bin/pip" install "${HAILO_APPS_VENDOR_PATH}"
}

download_resources() {
    log "Downloading CLIP models and resources..."
    # Use the vendored hailo-apps to download necessary models and resources
    # We do this as root to ensure they go to /usr/local/hailo/resources
    PYTHONPATH="${HAILO_APPS_VENDOR_PATH}" "${SERVICE_DIR}/venv/bin/python3" -c "
from hailo_apps.python.core.common.core import resolve_hef_path
from hailo_apps.python.core.common.defines import CLIP_PIPELINE
print('Downloading image encoder...')
resolve_hef_path('clip_vit_b_32_image_encoder', CLIP_PIPELINE)
print('Downloading text encoder...')
resolve_hef_path('clip_vit_b_32_text_encoder', CLIP_PIPELINE)
"
    
    local res_dir="/usr/local/hailo/resources"
    mkdir -p "${res_dir}/json" "${res_dir}/npy"
    
    log "Downloading CLIP support files (tokenizer, embeddings, projection)..."
    # Ensure they are not 0-byte or corrupted from previous failed attempts
    find "${res_dir}/json" "${res_dir}/npy" -size 0 -delete 2>/dev/null || true

    [ -f "${res_dir}/json/clip_tokenizer.json" ] || \
        curl -sL "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/configs/clip_tokenizer.json" -o "${res_dir}/json/clip_tokenizer.json"
    [ -f "${res_dir}/npy/token_embedding_lut.npy" ] || \
        curl -sL "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/npy/token_embedding_lut.npy" -o "${res_dir}/npy/token_embedding_lut.npy"
    [ -f "${res_dir}/npy/text_projection.npy" ] || \
        curl -sL "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/npy/text_projection.npy" -o "${res_dir}/npy/text_projection.npy"
    
    # Ensure readable by everyone but writable by root
    chmod -R 644 "${res_dir}/models/hailo10h"/clip* 2>/dev/null || true
    chmod -R 644 "${res_dir}/json"/clip* 2>/dev/null || true
    chmod -R 644 "${res_dir}/npy"/*.npy 2>/dev/null || true
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
    mkdir -p /var/lib/hailo-clip/{models,cache}
    mkdir -p /opt/hailo-clip

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-clip
    chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-clip

    # Copy service code if available
    if [[ -f "${SCRIPT_DIR}/hailo_clip_service.py" ]]; then
        cp "${SCRIPT_DIR}/hailo_clip_service.py" "${SERVICE_DIR}/"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/hailo_clip_service.py"
        chmod 0755 "${SERVICE_DIR}/hailo_clip_service.py"
    fi

    # Copy requirements.txt
    if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
        cp "${SCRIPT_DIR}/requirements.txt" "${SERVICE_DIR}/"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/requirements.txt"
    fi

    if [[ -f "${DEVICE_MANAGER_CLIENT_SRC}" ]]; then
        cp "${DEVICE_MANAGER_CLIENT_SRC}" "${SERVICE_DIR}/device_client.py"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/device_client.py"
        chmod 0644 "${SERVICE_DIR}/device_client.py"
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

path = "/etc/hailo/hailo-clip.yaml"
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    server = data.get("server", {}) if isinstance(data, dict) else {}
    port = server.get("port", 5000)
    print(int(port))
except Exception:
    print(5000)
PY
}

warn_if_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-clip.yaml if needed."
        fi
    fi
}

install_unit() {
    log "Installing systemd unit to ${UNIT_DEST}"
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"

    systemctl daemon-reload
    systemctl enable --now "${SERVICE_NAME}.service"

    # Ensure updated unit environment applies even if already running.
    systemctl restart "${SERVICE_NAME}.service"
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

    # Smoke-test that hailo-apps is importable as the service user.
    if command -v sudo >/dev/null 2>&1; then
        if ! sudo -u "${SERVICE_USER}" bash -lc "cd /var/lib/hailo-clip && '${SERVICE_DIR}/venv/bin/python3' -c 'import hailo_apps.python.pipeline_apps.clip.clip'" >/dev/null 2>&1; then
            warn "hailo-apps import check failed for ${SERVICE_USER}."
            warn "If this persists, check journal logs and confirm hailo-apps was installed into the venv."
        else
            log "✓ hailo-apps import check succeeded"
        fi
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
    preflight_clip_models

    create_user_group
    configure_device_permissions
    create_state_directories
    vendor_hailo_apps
    create_venv
    install_requirements
    download_resources
    install_config

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
    log "Service: systemctl status hailo-clip.service"
    log "Logs: journalctl -u hailo-clip.service -f"
}

main
