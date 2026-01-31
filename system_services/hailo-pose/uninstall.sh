#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-pose"
SERVICE_USER="hailo-pose"
SERVICE_GROUP="hailo-pose"
UNIT_DEST="/etc/systemd/system/hailo-pose.service"
ETC_HAILO_CONFIG="/etc/hailo/hailo-pose.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-pose"
INSTALL_TARGET="/usr/local/bin/hailo-pose-server"

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
        error "This script must be run as root (use: sudo ./uninstall.sh)"
        exit 1
    fi
}

stop_and_disable_service() {
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        log "Stopping ${SERVICE_NAME}.service"
        systemctl stop "${SERVICE_NAME}.service"
    fi

    if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        log "Disabling ${SERVICE_NAME}.service"
        systemctl disable "${SERVICE_NAME}.service"
    fi
}

remove_systemd_unit() {
    if [[ -f "${UNIT_DEST}" ]]; then
        log "Removing systemd unit: ${UNIT_DEST}"
        rm -f "${UNIT_DEST}"
        systemctl daemon-reload
    fi
}

remove_server_script() {
    if [[ -f "${INSTALL_TARGET}" ]]; then
        log "Removing server script: ${INSTALL_TARGET}"
        rm -f "${INSTALL_TARGET}"
    fi
}

remove_config_files() {
    if [[ -d "${ETC_XDG_DIR}" ]]; then
        log "Removing config directory: ${ETC_XDG_DIR}"
        rm -rf "${ETC_XDG_DIR}"
    fi

    if [[ -f "${ETC_HAILO_CONFIG}" ]]; then
        read -p "Remove YAML config at ${ETC_HAILO_CONFIG}? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log "Removing YAML config: ${ETC_HAILO_CONFIG}"
            rm -f "${ETC_HAILO_CONFIG}"
        else
            log "Keeping YAML config: ${ETC_HAILO_CONFIG}"
        fi
    fi
}

remove_state_directory() {
    if [[ -d "/var/lib/hailo-pose" ]]; then
        read -p "Remove service data directory /var/lib/hailo-pose? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log "Removing state directory: /var/lib/hailo-pose"
            rm -rf /var/lib/hailo-pose
        else
            log "Keeping state directory: /var/lib/hailo-pose"
        fi
    fi
}

remove_user_group() {
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Removing system user: ${SERVICE_USER}"
        userdel "${SERVICE_USER}" 2>/dev/null || warn "Failed to remove user ${SERVICE_USER}"
    fi

    if getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Removing system group: ${SERVICE_GROUP}"
        groupdel "${SERVICE_GROUP}" 2>/dev/null || warn "Failed to remove group ${SERVICE_GROUP}"
    fi
}

main() {
    require_root

    log "Uninstalling ${SERVICE_NAME}"
    stop_and_disable_service
    remove_systemd_unit
    remove_server_script
    remove_config_files
    remove_state_directory
    remove_user_group

    log "Uninstall complete"
}

main "$@"
