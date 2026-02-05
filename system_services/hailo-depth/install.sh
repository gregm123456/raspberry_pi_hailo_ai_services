#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-depth"
SERVICE_USER="hailo-depth"
SERVICE_GROUP="hailo-depth"
UNIT_SRC="${SCRIPT_DIR}/hailo-depth.service"
UNIT_DEST="/etc/systemd/system/hailo-depth.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-depth.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-depth"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-depth.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="11436"
SERVER_SCRIPT="${SCRIPT_DIR}/hailo_depth_server.py"
SERVICE_DIR="/opt/hailo-depth"
VENV_DIR="${SERVICE_DIR}/venv"
VENDOR_DIR="${SERVICE_DIR}/vendor"
HAILO_APPS_SRC="${SCRIPT_DIR}/../../hailo-apps"
HAILO_APPS_VENDOR_PATH="${VENDOR_DIR}/hailo-apps"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
INSTALL_TARGET="${VENV_DIR}/bin/python"

WARMUP_MODEL=""

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --warmup-model     Load model after install (optional)
  -h, --help         Show this help
EOF
}

log() {
    echo "[hailo-depth] $*"
}

warn() {
    echo "[hailo-depth] WARNING: $*" >&2
}

error() {
    echo "[hailo-depth] ERROR: $*" >&2
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

check_python_yaml() {
    require_command python3 "Install with: sudo apt install python3"
    if ! python3 - <<'PY' >/dev/null 2>&1
import yaml
PY
    then
        error "PyYAML is required. Install with: sudo apt install python3-yaml"
        exit 1
    fi
}

check_python_packages() {
    # Skip this check - packages will be installed in venv
    log "Python packages will be installed in venv"
}

create_venv() {
    log "Creating Python virtual environment with system site packages"
    mkdir -p "${SERVICE_DIR}"
    rm -rf "${VENV_DIR}"
    python3 -m venv --system-site-packages "${VENV_DIR}"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}"
}

vendor_hailo_apps() {
    log "Vendoring hailo-apps into ${HAILO_APPS_VENDOR_PATH}"
    # Ensure source exists
    if [[ ! -d "${HAILO_APPS_SRC}" ]]; then
        error "hailo-apps source not found at ${HAILO_APPS_SRC}. Is submodule initialized?"
        exit 1
    fi

    rm -rf "${HAILO_APPS_VENDOR_PATH}"
    mkdir -p "${VENDOR_DIR}"

    # Copy the hailo-apps repo into /opt so the systemd service user doesn't need
    # access to a developer home directory.
    cp -a "${HAILO_APPS_SRC}" "${VENDOR_DIR}/"

    # Patch resources path in vendored defines.py to use a writable directory
    # within the service's state directory.
    sed -i "s|RESOURCES_ROOT_PATH_DEFAULT = \"/usr/local/hailo/resources\"|RESOURCES_ROOT_PATH_DEFAULT = \"/var/lib/hailo-depth/resources\"|g" "${HAILO_APPS_VENDOR_PATH}/hailo_apps/python/core/common/defines.py" || log "Note: defines.py path may differ"

    # Fix package structure by adding missing __init__.py files
    # These are required for proper namespacing and module resolution
    touch "${HAILO_APPS_VENDOR_PATH}/hailo_apps/__init__.py" 2>/dev/null || true
    touch "${HAILO_APPS_VENDOR_PATH}/hailo_apps/python/__init__.py" 2>/dev/null || true
    touch "${HAILO_APPS_VENDOR_PATH}/hailo_apps/python/core/__init__.py" 2>/dev/null || true

    # Ensure readable by the service user
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${VENDOR_DIR}"
    chmod -R u+rX,g+rX,o-rwx "${VENDOR_DIR}"

    log "✓ hailo-apps vendored successfully"
}

install_python_packages() {
    log "Installing Python packages into venv"
    
    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        error "requirements.txt not found at ${REQUIREMENTS_FILE}"
        exit 1
    fi

    # Use venv Python to install packages
    "${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel
    "${VENV_DIR}/bin/pip" install -r "${REQUIREMENTS_FILE}"
    
    log "✓ Python packages installed"
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

preflight_hailo_hailort() {
    # Check for HailoRT Python bindings in system site-packages
    if ! python3 - <<'PY' >/dev/null 2>&1
try:
    import hailo_platform
    print("OK")
except ImportError:
    raise
PY
    then
        error "HailoRT Python bindings (hailo_platform) not found in system site-packages."
        error ""
        error "Ensure python3-h10-hailort or python3-hailo is installed:"
        error "  sudo apt install python3-h10-hailort"
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
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-depth -g "${SERVICE_GROUP}" "${SERVICE_USER}"
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
    log "Creating service directory structure"
    mkdir -p /var/lib/hailo-depth/resources/models
    mkdir -p /var/lib/hailo-depth/resources/postprocess
    mkdir -p /var/lib/hailo-depth/cache

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-depth
    chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-depth
}

download_models() {
    log "Downloading model artifacts from Hailo Model Zoo"
    local model_dir="/var/lib/hailo-depth/resources/models"
    local model_name="${1:-scdepthv3}"
    local hef_file="${model_dir}/${model_name}.hef"
    
    # Check if model already exists
    if [[ -f "${hef_file}" ]]; then
        log "✓ Model ${model_name} already exists at ${hef_file}"
        return 0
    fi
    
    # Model download URLs for Hailo-10H, v5.2.0 (declared with declare -A)
    declare -A model_urls
    model_urls[scdepthv3]="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/scdepthv3.hef"
    model_urls[fast_depth]="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/fast_depth.hef"
    
    if [[ -z "${model_urls[$model_name]}" ]]; then
        error "Unknown model: ${model_name}. Available: $(echo "${!model_urls[@]}" | tr ' ' ', ')"
        return 1
    fi
    
    local url="${model_urls[$model_name]}"
    log "Downloading ${model_name}.hef from Hailo Model Zoo"
    log "  URL: ${url}"
    log "  Destination: ${hef_file}"
    
    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required to download models. Install with: sudo apt install curl"
        return 1
    fi
    
    if ! curl -fsSL --progress-bar -o "${hef_file}" "${url}"; then
        error "Failed to download model from ${url}"
        rm -f "${hef_file}"
        return 1
    fi
    
    # Verify download
    local file_size
    file_size=$(stat -c%s "${hef_file}" 2>/dev/null)
    if [[ ${file_size} -lt 1000000 ]]; then
        error "Downloaded file seems too small (${file_size} bytes). May be corrupted."
        rm -f "${hef_file}"
        return 1
    fi
    
    log "✓ Model downloaded successfully: $((file_size / 1024 / 1024)) MB"
    
        # Fix ownership to service user
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${hef_file}"
        chmod 644 "${hef_file}"
    return 0
}

validate_model_hef() {
    local hef_file="$1"
    
    if [[ ! -f "${hef_file}" ]]; then
        warn "HEF file not found at ${hef_file}"
        return 1
    fi
    
    log "Validating HEF file: ${hef_file}"
    local file_size
    file_size=$(stat -c%s "${hef_file}")
    
    if [[ ${file_size} -lt 1000000 ]]; then
        warn "HEF file seems small (${file_size} bytes), may be invalid"
        return 1
    fi
    
    log "✓ HEF file size OK: $((file_size / 1024 / 1024)) MB"
    return 0
}

copy_postprocess_files() {
    log "Setting up postprocess libraries"
    local postprocess_dir="/var/lib/hailo-depth/resources/postprocess"
    
    # TODO: Copy or compile postprocess libraries
    # Source: /opt/hailo-depth/vendor/hailo-apps/hailo_apps/python/postprocess/
    
    log "Note: Postprocess libraries will be resolved at runtime (Phase 2)"
    return 0
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
    log "Installing server script to ${SERVICE_DIR}"
    
    if [[ ! -f "${SERVER_SCRIPT}" ]]; then
        error "Server script not found: ${SERVER_SCRIPT}"
        exit 1
    fi

    install -m 0755 "${SERVER_SCRIPT}" "${SERVICE_DIR}/hailo_depth_server.py"
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/hailo_depth_server.py"
}

get_config_port() {
    python3 - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
import sys

path = "/etc/hailo/hailo-depth.yaml"
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
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-depth.yaml if needed."
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
        for attempt in {1..5}; do
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

warmup_model() {
    local port="$1"
    log "Warmup: loading model into memory"
    sleep 2  # Give service time to start
    curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1 || warn "Warmup health check failed"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --warmup-model)
                WARMUP_MODEL="true"
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
    preflight_hailo
    preflight_hailo_hailort
    check_python_yaml

    create_user_group
    create_venv
    install_python_packages
    vendor_hailo_apps

    configure_device_permissions
    create_state_directories
    download_models "scdepthv3"
    validate_model_hef "/var/lib/hailo-depth/resources/models/scdepthv3.hef"
    copy_postprocess_files
    install_config
    install_server_script

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    if [[ -n "${WARMUP_MODEL}" ]]; then
        warmup_model "${port}" || warn "Warmup failed; service may still be loading"
    fi

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
    log "Service directory: ${SERVICE_DIR}"
    log "Start service: sudo systemctl start ${SERVICE_NAME}.service"
    log "View logs: sudo journalctl -u ${SERVICE_NAME}.service -f"
    log "API endpoint: POST http://localhost:${port}/v1/depth/estimate"
}

main "$@"
