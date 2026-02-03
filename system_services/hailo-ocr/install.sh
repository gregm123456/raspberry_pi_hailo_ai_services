#!/usr/bin/env bash
set -euo pipefail

# Hailo-10H NPU Accelerated OCR Service Installer
# Philosophy: Pragmatic, modular, and isolated using venv and vendoring.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Constants
SERVICE_NAME="hailo-ocr"
SERVICE_USER="hailo-ocr"
SERVICE_GROUP="hailo-ocr"
INSTALL_DIR="/opt/hailo-ocr"
DATA_DIR="/var/lib/hailo-ocr"
RESOURCES_DIR="${DATA_DIR}/resources"
VENV_DIR="${INSTALL_DIR}/venv"
VENDOR_DIR="${INSTALL_DIR}/vendor"
HAILO_APPS_SRC="${REPO_ROOT}/hailo-apps"

# Files
UNIT_SRC="${SCRIPT_DIR}/hailo-ocr.service"
UNIT_DEST="/etc/systemd/system/${SERVICE_NAME}.service"
CONFIG_SRC="${SCRIPT_DIR}/config.yaml"
ETC_CONFIG="/etc/hailo/hailo-ocr.yaml"
XDG_CONFIG_DIR="/etc/xdg/hailo-ocr"
JSON_CONFIG="${XDG_CONFIG_DIR}/hailo-ocr.json"

WARMUP_MODELS=""

# Logging
log() { echo -e "\033[0;32m[hailo-ocr]\033[0m $*"; }
error() { echo -e "\033[0;31m[hailo-ocr] ERROR:\033[0m $*" >&2; exit 1; }

# Prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    if [[ ${EUID} -ne 0 ]]; then error "Must be run as root (use sudo)"; fi
    
    if ! command -v hailortcli > /dev/null; then
        error "hailortcli not found. Please install HailoRT first."
    fi
    
    if ! hailortcli fw-control identify > /dev/null 2>&1; then
        error "Hailo-10H device not detected or driver not loaded."
    fi
    
    log "Hailo-10H detected successfully."
}

setup_structure() {
    log "Creating directory structure..."
    mkdir -p "${INSTALL_DIR}" "${DATA_DIR}" "${RESOURCES_DIR}" "${XDG_CONFIG_DIR}" "/etc/hailo"
    
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        useradd -r -s /usr/sbin/nologin -d "${DATA_DIR}" -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
    
    # Add user to NPU device group for access
    local device_group
    device_group=$(stat -c '%G' /dev/hailo0)
    if ! getent group "${device_group}" >/dev/null; then
        error "Device group '${device_group}' not found. Check Hailo installation/udev rules."
    fi
    
    log "Adding ${SERVICE_USER} to ${device_group} group"
    usermod -aG "${device_group}" "${SERVICE_USER}"
}

setup_venv() {
    log "Setting up virtual environment..."
    python3 -m venv --system-site-packages "${VENV_DIR}"
    
    # Upgrade pip
    "${VENV_DIR}/bin/pip" install --upgrade pip
    
    # Install requirements
    if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
        log "Installing requirements from requirements.txt..."
        "${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"
    fi
}

vendor_hailo_apps() {
    log "Vendoring hailo-apps..."
    mkdir -p "${VENDOR_DIR}"
    cp -r "${HAILO_APPS_SRC}" "${VENDOR_DIR}/"
    
    # Patch: Remove symspellpy dependency from paddle_ocr_utils
    log "Patching out symspellpy dependency..."
    local paddle_ocr_utils="${VENDOR_DIR}/hailo-apps/hailo_apps/python/standalone_apps/paddle_ocr/paddle_ocr_utils.py"
    "${VENV_DIR}/bin/python3" - "${paddle_ocr_utils}" << 'PATCHEOF'
import re
import sys

paddle_ocr_utils = sys.argv[1]

with open(paddle_ocr_utils, 'r') as f:
    content = f.read()

# Remove symspellpy import
content = re.sub(r'from symspellpy import SymSpell\n', '', content)

# Comment out OcrCorrector class
lines = content.split('\n')
result = []
in_class = False

for line in lines:
    if line.startswith('class OcrCorrector:'):
        in_class = True
        result.append('# ' + line)
    elif in_class:
        if line and not line[0].isspace() and (line.startswith('class ') or line.startswith('def ')):
            in_class = False
            result.append(line)
        elif line.strip() and not line.strip().startswith('#'):
            result.append('# ' + line)
        else:
            result.append(line)
    else:
        result.append(line)

with open(paddle_ocr_utils, 'w') as f:
    f.write('\n'.join(result))

print("✓ Patched symspellpy")
PATCHEOF
    
    # Install vendored hailo-apps in editable mode
    log "Installing vendored hailo-apps..."
    "${VENV_DIR}/bin/pip" install -e "${VENDOR_DIR}/hailo-apps"
}

download_resources() {
    log "Downloading HEF models and resources..."
    
    # Create models directory with proper permissions first
    mkdir -p "${RESOURCES_DIR}/models"
    chmod 755 "${RESOURCES_DIR}"
    chmod 755 "${RESOURCES_DIR}/models"
    
    # Set environment variable to tell hailo-apps where to download
    export RESOURCES_PATH="${RESOURCES_DIR}"
    
    # Download OCR models using hailo-apps (as root for permissions)
    log "Downloading OCR detection model..."
    "${VENV_DIR}/bin/python3" -m hailo_apps.installation.download_resources \
        --arch hailo10h \
        --group paddle_ocr \
        --resource-type model \
        --resource-name ocr_det \
        --no-parallel || log "Warning: ocr_det download had issues (may retry)"
    
    log "Downloading OCR recognition model..."
    "${VENV_DIR}/bin/python3" -m hailo_apps.installation.download_resources \
        --arch hailo10h \
        --group paddle_ocr \
        --resource-type model \
        --resource-name ocr \
        --no-parallel || log "Warning: ocr download had issues (may retry)"
    
    # Verify models exist and are readable (they go into hailo10h subdirectory)
    if [[ ! -f "${RESOURCES_DIR}/models/hailo10h/ocr_det.hef" ]] || [[ ! -f "${RESOURCES_DIR}/models/hailo10h/ocr.hef" ]]; then
        log "ERROR: OCR HEF models were not downloaded successfully."
        log "Expected location: ${RESOURCES_DIR}/models/hailo10h/"
        log "Please ensure the download completed and try: sudo ${VENV_DIR}/bin/python3 -m hailo_apps.installation.download_resources --arch hailo10h --group paddle_ocr --no-parallel"
        exit 1
    else
        log "✓ HEF models downloaded successfully to ${RESOURCES_DIR}/models/hailo10h/"
    fi
    
    # Set final ownership to service user
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${RESOURCES_DIR}"
    chmod 755 "${RESOURCES_DIR}/models"
}

install_files() {
    log "Installing service files..."
    
    # 1. Config: Copy YAML config if not already present
    if [[ ! -f "${ETC_CONFIG}" ]]; then
        install -m 0644 "${CONFIG_SRC}" "${ETC_CONFIG}"
    else
        log "Config ${ETC_CONFIG} already exists, skipping."
    fi
    
    # 2. Render JSON config from YAML
    log "Rendering JSON config..."
    mkdir -p "${XDG_CONFIG_DIR}"
    
    "${VENV_DIR}/bin/python3" << RENDER_CONFIG
import yaml
import json

try:
    with open("${ETC_CONFIG}", "r") as f:
        config = yaml.safe_load(f)
    
    with open("${JSON_CONFIG}", "w") as f:
        json.dump(config, f, indent=2)
    
    print("✓ Generated ${JSON_CONFIG}")
except Exception as e:
    print(f"ERROR: Failed to render config: {e}")
    exit(1)
RENDER_CONFIG
    
    # 3. Install server script
    install -m 0755 "${SCRIPT_DIR}/hailo_ocr_server.py" "${INSTALL_DIR}/hailo_ocr_server.py"
    
    # 4. Set permissions
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}" "${DATA_DIR}"
    chmod 755 "${INSTALL_DIR}"
    chmod 755 "${DATA_DIR}"
    
    # Ensure config is readable
    chmod 644 "${JSON_CONFIG}"
}

install_systemd_unit() {
    log "Installing systemd service unit..."
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"
    
    # Reload systemd
    systemctl daemon-reload
    
    log "Service installed. Enable with: sudo systemctl enable ${SERVICE_NAME}"
    log "Start with: sudo systemctl start ${SERVICE_NAME}"
}

# Main execution
main() {
    log "Starting Hailo-10H OCR Service installation..."
    check_prerequisites
    setup_structure
    setup_venv
    vendor_hailo_apps
    download_resources
    install_files
    install_systemd_unit
    log "Installation complete!"
}

main "$@"
