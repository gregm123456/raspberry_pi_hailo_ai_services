#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-device-manager"
SERVICE_USER="hailo-device-mgr"
SERVICE_GROUP="hailo-device-mgr"
UNIT_SRC="${SCRIPT_DIR}/hailo-device-manager.service"
UNIT_DEST="/etc/systemd/system/hailo-device-manager.service"
SERVICE_DIR="/opt/hailo-device-manager"
MANAGER_SCRIPT="${SCRIPT_DIR}/hailo_device_manager.py"
CLIENT_SCRIPT="${SCRIPT_DIR}/device_client.py"
ENV_FILE="/etc/hailo/device-manager.env"

log() {
    echo "[hailo-device-manager] $*"
}

warn() {
    echo "[hailo-device-manager] WARNING: $*" >&2
}

error() {
    echo "[hailo-device-manager] ERROR: $*" >&2
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

preflight_hailo_hailort() {
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
        error "Ensure python3-h10-hailort is installed:"
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
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-device-manager -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
}

create_venv() {
    log "Creating Python virtual environment with system site packages"
    mkdir -p "${SERVICE_DIR}"
    rm -rf "${SERVICE_DIR}/venv"
    python3 -m venv --system-site-packages "${SERVICE_DIR}/venv"
    chown -R root:root "${SERVICE_DIR}/venv"
}

copy_scripts() {
    log "Copying manager and client scripts"
    cp "${MANAGER_SCRIPT}" "${SERVICE_DIR}/"
    cp "${CLIENT_SCRIPT}" "${SERVICE_DIR}/"
    
    chmod 0755 "${SERVICE_DIR}/hailo_device_manager.py"
    chmod 0644 "${SERVICE_DIR}/device_client.py"
    
    chown -R root:root "${SERVICE_DIR}"
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
    mkdir -p /var/lib/hailo-device-manager
    mkdir -p /run/hailo
    mkdir -p /etc/hailo

    chown "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-device-manager
    chmod u+rwX,g+rX,o-rwx /var/lib/hailo-device-manager
    
    # Runtime socket directory will be created by systemd
    # but we pre-create it here to set permissions
    mkdir -p /run/hailo
    chown root:root /run/hailo
    chmod 0755 /run/hailo
}

write_env_file() {
    local device_group
    device_group=$(stat -c '%G' /dev/hailo0)

    log "Writing ${ENV_FILE}"
    cat >"${ENV_FILE}" <<EOF
# Optional overrides for hailo-device-manager
HAILO_DEVICE_SOCKET=/run/hailo/device.sock
HAILO_DEVICE_SOCKET_MODE=0660
HAILO_DEVICE_SOCKET_GROUP=${device_group}
EOF

    chmod 0644 "${ENV_FILE}"
}

install_unit() {
    log "Installing systemd unit to ${UNIT_DEST}"
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}.service"
    systemctl restart "${SERVICE_NAME}.service"
}

verify_service() {
    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service failed to start. Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
        return 1
    fi

    # Check if socket was created
    if [[ ! -e /run/hailo/device.sock ]]; then
        error "Device manager socket not created at /run/hailo/device.sock"
        return 1
    fi

    log "✓ Device manager socket ready: /run/hailo/device.sock"
    log "✓ Service is running"
}

main() {
    require_root
    require_command python3 "Install with: sudo apt install python3"
    require_command systemctl "This script requires systemd"
    
    preflight_hailo
    preflight_hailo_hailort

    create_user_group
    configure_device_permissions
    create_state_directories
    write_env_file
    create_venv
    copy_scripts
    install_unit
    verify_service

    log "Install complete."
    log "Start service: sudo systemctl start ${SERVICE_NAME}.service"
    log "View logs: sudo journalctl -u ${SERVICE_NAME}.service -f"
    log ""
    log "Services can now use the device manager instead of direct device access."
    log "Update service code to use device_client.HailoDeviceClient"
}

main "$@"
