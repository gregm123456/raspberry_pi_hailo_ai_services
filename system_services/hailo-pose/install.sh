#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SERVICE_NAME="hailo-pose"
SERVICE_USER="hailo-pose"
SERVICE_GROUP="hailo-pose"
SERVICE_DIR="/opt/hailo-pose"
DATA_DIR="/var/lib/hailo-pose"
RESOURCES_DIR="${DATA_DIR}/resources"
VENV_DIR="${SERVICE_DIR}/venv"
VENDOR_DIR="${SERVICE_DIR}/vendor"
HAILO_APPS_SRC="${REPO_ROOT}/hailo-apps"
HAILO_APPS_VENDOR_PATH="${VENDOR_DIR}/hailo-apps"

UNIT_SRC="${SCRIPT_DIR}/hailo-pose.service"
UNIT_DEST="/etc/systemd/system/hailo-pose.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-pose.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-pose"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-pose.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="11436"
SERVER_SCRIPT="${SCRIPT_DIR}/hailo_pose_service.py"
REQUIREMENTS_SRC="${SCRIPT_DIR}/requirements.txt"

WARMUP_MODEL=""

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --warmup    Wait for readiness after install
  -h, --help  Show this help
EOF
}

log() {
    echo "[hailo-pose] $*"
}

warn() {
    echo "[hailo-pose] WARNING: $*" >&2
}

error() {
    echo "[hailo-pose] ERROR: $*" >&2
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

preflight_hailort() {
    if ! python3 - <<'PY' >/dev/null 2>&1
try:
    import hailo_platform
    print("OK")
except ImportError:
    raise
PY
    then
        error "HailoRT Python bindings (hailo_platform) not found in system site-packages."
        error "Install with: sudo apt install python3-h10-hailort"
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

create_state_directories() {
    log "Creating service directory structure"
    mkdir -p "${RESOURCES_DIR}/models/hailo10h"
    mkdir -p "${DATA_DIR}/cache"
    mkdir -p "${SERVICE_DIR}"

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${DATA_DIR}"
    chmod -R u+rwX,g+rX,o-rwx "${DATA_DIR}"

    cp "${SERVER_SCRIPT}" "${SERVICE_DIR}/"
    cp "${RENDER_SCRIPT}" "${SERVICE_DIR}/"
    cp "${REQUIREMENTS_SRC}" "${SERVICE_DIR}/"

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}"
    chmod 0755 "${SERVICE_DIR}/hailo_pose_service.py"
}

create_venv() {
    log "Creating Python virtual environment with system site packages"
    rm -rf "${VENV_DIR}"
    python3 -m venv --system-site-packages "${VENV_DIR}"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${VENV_DIR}"
}

vendor_hailo_apps() {
    log "Vendoring hailo-apps into ${HAILO_APPS_VENDOR_PATH}"
    if [[ ! -d "${HAILO_APPS_SRC}" ]]; then
        error "hailo-apps source not found at ${HAILO_APPS_SRC}. Is submodule initialized?"
        exit 1
    fi

    rm -rf "${HAILO_APPS_VENDOR_PATH}"
    mkdir -p "${VENDOR_DIR}"
    cp -a "${HAILO_APPS_SRC}" "${VENDOR_DIR}/"

    sed -i "s|RESOURCES_ROOT_PATH_DEFAULT = \"/usr/local/hailo/resources\"|RESOURCES_ROOT_PATH_DEFAULT = \"${RESOURCES_DIR}\"|g" \
        "${HAILO_APPS_VENDOR_PATH}/hailo_apps/python/core/common/defines.py"

    touch "${HAILO_APPS_VENDOR_PATH}/hailo_apps/__init__.py"
    touch "${HAILO_APPS_VENDOR_PATH}/hailo_apps/python/__init__.py"
    touch "${HAILO_APPS_VENDOR_PATH}/hailo_apps/python/core/__init__.py"

    chown -R root:root "${HAILO_APPS_VENDOR_PATH}"
    chmod -R u+rwX,go+rX,go-w "${HAILO_APPS_VENDOR_PATH}"
}

install_requirements() {
    log "Installing Python requirements in venv"
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -r "${SERVICE_DIR}/requirements.txt"

    log "Installing vendored hailo-apps into venv"
    "${VENV_DIR}/bin/pip" install "${HAILO_APPS_VENDOR_PATH}"
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

get_config_port() {
    "${VENV_DIR}/bin/python3" - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml

path = "/etc/hailo/hailo-pose.yaml"
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
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-pose.yaml if needed."
        fi
    fi
}

resolve_config_model_name() {
    "${VENV_DIR}/bin/python3" - <<'PY' 2>/dev/null || echo ""
import yaml

path = "/etc/hailo/hailo-pose.yaml"
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    model = data.get("model", {}) if isinstance(data, dict) else {}
    name = model.get("name", "")
    print(name)
except Exception:
    print("")
PY
}

resolve_default_model_name() {
    "${VENV_DIR}/bin/python3" - <<'PY' 2>/dev/null || echo ""
from hailo_apps.config.config_manager import get_default_model_name
print(get_default_model_name("pose_estimation", "hailo10h") or "")
PY
}

ensure_model_downloaded() {
    local model_name
    model_name="$(resolve_config_model_name)"

    if [[ -z "${model_name}" ]]; then
        model_name="$(resolve_default_model_name)"
    fi

    if [[ -z "${model_name}" ]]; then
        warn "No model name resolved; skipping model download"
        return 0
    fi

    local model_path
    model_path="${RESOURCES_DIR}/models/hailo10h/${model_name}.hef"
    if [[ -f "${model_path}" ]]; then
        log "Model already present: ${model_path}"
        return 0
    fi

    log "Downloading model: ${model_name}"
    "${VENV_DIR}/bin/python3" -m hailo_apps.installation.download_resources \
        --group pose_estimation \
        --arch hailo10h \
        --resource-type model \
        --resource-name "${model_name}" \
        --no-parallel

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${RESOURCES_DIR}"
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
    log "Warmup: waiting for readiness"
    sleep 2
    curl -fsS "http://localhost:${port}/health/ready" >/dev/null 2>&1 || warn "Warmup readiness check failed"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --warmup)
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
    require_command python3 "Install with: sudo apt install python3"

    preflight_hailo
    preflight_hailort

    create_user_group
    configure_device_permissions
    create_state_directories
    create_venv
    vendor_hailo_apps
    install_requirements
    install_config
    ensure_model_downloaded

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    if [[ -n "${WARMUP_MODEL}" ]]; then
        warmup_model "${port}" || warn "Warmup failed; service may still be loading"
    fi

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
    log "Start service: sudo systemctl start ${SERVICE_NAME}.service"
    log "View logs: sudo journalctl -u ${SERVICE_NAME}.service -f"
}

main "$@"
