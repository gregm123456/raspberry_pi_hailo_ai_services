#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-vision"
SERVICE_USER="hailo-vision"
SERVICE_GROUP="hailo-vision"
UNIT_DEST="/etc/systemd/system/hailo-vision.service"
INSTALL_TARGET="/usr/local/bin/hailo-vision-server"

REMOVE_USER=false
PURGE_DATA=false

usage() {
    cat <<'EOF'
Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --remove-user      Remove the hailo-vision system user and group
  --purge-data       Remove all service data (/var/lib/hailo-vision)
  -h, --help         Show this help
EOF
}

log() {
    echo "[hailo-vision] $*"
}

warn() {
    echo "[hailo-vision] WARNING: $*" >&2
}

error() {
    echo "[hailo-vision] ERROR: $*" >&2
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "This script must be run as root (use: sudo ./uninstall.sh)"
        exit 1
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --remove-user)
                REMOVE_USER=true
                shift
                ;;
            --purge-data)
                PURGE_DATA=true
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

stop_service() {
    if systemctl is-enabled "${SERVICE_NAME}.service" 2>/dev/null; then
        log "Disabling service"
        systemctl disable "${SERVICE_NAME}.service"
    fi

    if systemctl is-active "${SERVICE_NAME}.service" 2>/dev/null; then
        log "Stopping service"
        systemctl stop "${SERVICE_NAME}.service"
    fi

    log "Reloading systemd"
    systemctl daemon-reload
}

remove_unit() {
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

remove_user_group() {
    if [[ "${REMOVE_USER}" == true ]]; then
        if id "${SERVICE_USER}" >/dev/null 2>&1; then
            log "Removing system user ${SERVICE_USER}"
            userdel "${SERVICE_USER}" || warn "Failed to remove user (may have running processes)"
        fi

        if getent group "${SERVICE_GROUP}" >/dev/null; then
            log "Removing system group ${SERVICE_GROUP}"
            groupdel "${SERVICE_GROUP}"
        fi
    else
        log "Skipping user/group removal (use --remove-user to remove)"
    fi
}

purge_data() {
    if [[ "${PURGE_DATA}" == true ]]; then
        log "Removing service data and state"
        rm -rf /var/lib/hailo-vision
        log "Removed: /var/lib/hailo-vision"
    else
        log "Skipping data purge (use --purge-data to remove)"
    fi
}

main() {
    parse_args "$@"
    require_root

    stop_service
    remove_unit
    remove_server_script
    remove_user_group
    purge_data

    log "Uninstall complete"
}

main "$@"
