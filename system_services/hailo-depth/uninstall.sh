#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-depth"
SERVICE_USER="hailo-depth"
SERVICE_GROUP="hailo-depth"
UNIT_DEST="/etc/systemd/system/hailo-depth.service"
ETC_HAILO_CONFIG="/etc/hailo/hailo-depth.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-depth"
INSTALL_TARGET="/usr/local/bin/hailo-depth-server"

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
        error "This script must be run as root (use: sudo ./uninstall.sh)"
        exit 1
    fi
}

main() {
    require_root

    log "Stopping and disabling service"
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        systemctl stop "${SERVICE_NAME}.service"
    fi
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        systemctl disable "${SERVICE_NAME}.service"
    fi

    log "Removing systemd unit"
    if [[ -f "${UNIT_DEST}" ]]; then
        rm -f "${UNIT_DEST}"
        systemctl daemon-reload
    fi

    log "Removing server binary"
    if [[ -f "${INSTALL_TARGET}" ]]; then
        rm -f "${INSTALL_TARGET}"
    fi

    log "Removing configuration (optional: comment to keep)"
    if [[ -f "${ETC_HAILO_CONFIG}" ]]; then
        rm -f "${ETC_HAILO_CONFIG}"
    fi
    if [[ -d "${ETC_XDG_DIR}" ]]; then
        rm -rf "${ETC_XDG_DIR}"
    fi

    log "Removing state directory (optional: comment to keep cached data)"
    if [[ -d "/var/lib/hailo-depth" ]]; then
        rm -rf "/var/lib/hailo-depth"
    fi

    log "Removing user and group"
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        userdel "${SERVICE_USER}" || warn "Could not remove user ${SERVICE_USER}"
    fi
    if getent group "${SERVICE_GROUP}" >/dev/null; then
        groupdel "${SERVICE_GROUP}" || warn "Could not remove group ${SERVICE_GROUP}"
    fi

    log "Uninstall complete"
}

main "$@"
