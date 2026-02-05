#!/usr/bin/env bash
# hailo-florence Installation Script
# Installs Florence-2 captioning + VQA service for Raspberry Pi 5 + Hailo-10H

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-florence"
SERVICE_USER="hailo-florence"
SERVICE_GROUP="hailo-florence"
SERVICE_DIR="/opt/hailo-florence"
DATA_DIR="/var/lib/hailo-florence"
MODEL_DIR="${DATA_DIR}/models"
PROCESSOR_REPO="microsoft/florence-2-base"
VENV_DIR="${SERVICE_DIR}/venv"

UNIT_SRC="${SCRIPT_DIR}/hailo-florence.service"
UNIT_DEST="/etc/systemd/system/hailo-florence.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-florence.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-florence"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-florence.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
SERVER_SCRIPT="${SCRIPT_DIR}/hailo_florence_service.py"
REQUIREMENTS_SRC="${SCRIPT_DIR}/requirements.txt"

log() {
    echo "[hailo-florence] $*"
}

warn() {
    echo "[hailo-florence] WARNING: $*" >&2
}

error() {
    echo "[hailo-florence] ERROR: $*" >&2
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

create_user_group() {
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Creating system group ${SERVICE_GROUP}"
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Creating system user ${SERVICE_USER}"
        useradd -r -s /usr/sbin/nologin -d "${DATA_DIR}" -g "${SERVICE_GROUP}" "${SERVICE_USER}"
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

create_directories() {
    log "Creating service directories"
    mkdir -p "${SERVICE_DIR}" "${DATA_DIR}" "${MODEL_DIR}"

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${DATA_DIR}"
    chmod -R u+rwX,g+rX,o-rwx "${DATA_DIR}"
    chmod 0755 "${DATA_DIR}"

    cp "${SERVER_SCRIPT}" "${SERVICE_DIR}/"
    cp "${RENDER_SCRIPT}" "${SERVICE_DIR}/"
    cp "${REQUIREMENTS_SRC}" "${SERVICE_DIR}/"

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}"
    chmod 0755 "${SERVICE_DIR}/hailo_florence_service.py"
}

create_venv() {
    log "Creating Python virtual environment with system site packages"
    rm -rf "${VENV_DIR}"
    python3 -m venv --system-site-packages "${VENV_DIR}"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${VENV_DIR}"
}

install_requirements() {
    log "Installing Python requirements in venv"
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -r "${SERVICE_DIR}/requirements.txt"
}

download_resources() {
    log "Downloading Florence-2 resources"

    local urls=(
        "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/hackathon/dynamic_captioning/caption_embedding.npy"
        "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/hackathon/dynamic_captioning/word_embedding.npy"
        "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/hackathon/dynamic_captioning/florence2_transformer_decoder.hef"
        "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/hackathon/dynamic_captioning/florence2_transformer_encoder.hef"
        "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/hackathon/dynamic_captioning/vision_encoder.onnx"
        "https://hailo-csdata.s3.eu-west-2.amazonaws.com/resources/hackathon/dynamic_captioning/tokenizer.json"
    )

    for url in "${urls[@]}"; do
        local filename
        filename=$(basename "${url}")
        local dest="${MODEL_DIR}/${filename}"
        if [[ -f "${dest}" ]]; then
            log "Resource already present: ${dest}"
            continue
        fi
        log "Downloading ${filename}"
        curl -sL "${url}" -o "${dest}"
    done

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${MODEL_DIR}"
    chmod -R u+rwX,g+rX,o-rwx "${MODEL_DIR}"
}

download_processor() {
    log "Downloading Florence-2 processor artifacts"

    local processor_dir
    processor_dir="${MODEL_DIR}/processor/${PROCESSOR_REPO//\//__}"

    if [[ -f "${processor_dir}/preprocessor_config.json" && -f "${processor_dir}/processing_florence2.py" ]]; then
        log "Processor already present: ${processor_dir}"
        return
    fi

    mkdir -p "${processor_dir}"

    HUGGINGFACE_HUB_DISABLE_TELEMETRY=1 "${VENV_DIR}/bin/python3" - <<PY
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="${PROCESSOR_REPO}",
    local_dir="${processor_dir}",
    local_dir_use_symlinks=False,
    allow_patterns=[
        "*.json",
        "*.txt",
        "*.model",
        "*.py",
        "tokenizer.json",
        "vocab.*",
        "merges.*",
    ],
)
PY

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${processor_dir}"
    chmod -R u+rwX,g+rX,o-rwx "${processor_dir}"
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
    "${VENV_DIR}/bin/python3" "${RENDER_SCRIPT}" --input "${ETC_HAILO_CONFIG}" --output "${JSON_CONFIG}"
}

install_unit() {
    log "Installing systemd unit to ${UNIT_DEST}"
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"
    systemctl daemon-reload
}

main() {
    require_root
    require_command python3 "Install with: sudo apt install python3"
    require_command curl "Install with: sudo apt install curl"
    preflight_hailo

    create_user_group
    configure_device_permissions
    create_directories
    create_venv
    install_requirements
    download_resources
    download_processor
    install_config
    install_unit

    log "Install prep complete. Next steps:"
    log "  sudo systemctl enable --now ${SERVICE_NAME}.service"
    log "  sudo systemctl status ${SERVICE_NAME}.service"
    log "  curl http://localhost:11438/health"
}

main
