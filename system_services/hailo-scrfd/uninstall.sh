#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-scrfd"
SERVICE_USER="hailo-scrfd"
SERVICE_GROUP="hailo-scrfd"
UNIT_DEST="/etc/systemd/system/hailo-scrfd.service"
ETC_HAILO_CONFIG="/etc/hailo/hailo-scrfd.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-scrfd"
SERVICE_DIR="/opt/hailo-scrfd"
STATE_DIR="/var/lib/hailo-scrfd"

usage() {
    cat <<'EOF'
Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --remove-user   Remove hailo-scrfd system user/group
  --purge-data    Delete all service data from /var/lib/hailo-scrfd
  -h, --help      Show this help
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

remove_unit() {
    if [[ -f "${UNIT_DEST}" ]]; then
        log "Removing systemd unit: ${UNIT_DEST}"
        rm -f "${UNIT_DEST}"
        systemctl daemon-reload
    fi
}

remove_config() {
    if [[ -f "${ETC_HAILO_CONFIG}" ]]; then
        log "Removing config: ${ETC_HAILO_CONFIG}"
        rm -f "${ETC_HAILO_CONFIG}"
    fi
    
    if [[ -d "${ETC_XDG_DIR}" ]]; then
        log "Removing XDG config: ${ETC_XDG_DIR}"
        rm -rf "${ETC_XDG_DIR}"
    fi
}

remove_service_code() {
    if [[ -d "${SERVICE_DIR}" ]]; then
        log "Removing service code: ${SERVICE_DIR}"
        rm -rf "${SERVICE_DIR}"
    fi
}

remove_user_group() {
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Removing user: ${SERVICE_USER}"
        userdel "${SERVICE_USER}"
    fi
    
    if getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
        log "Removing group: ${SERVICE_GROUP}"
        groupdel "${SERVICE_GROUP}"
    fi
}

purge_data() {
    if [[ -d "${STATE_DIR}" ]]; then
        log "Purging service data: ${STATE_DIR}"
        rm -rf "${STATE_DIR}"
    fi
}

parse_args() {
    REMOVE_USER="false"
    PURGE_DATA="false"
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --remove-user)
                REMOVE_USER="true"
                shift
                ;;
            --purge-data)
                PURGE_DATA="true"
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
    local REMOVE_USER="false"
    local PURGE_DATA="false"
    
    parse_args "$@"
    
    require_root
    
    stop_and_disable_service
    remove_unit
    remove_config
    remove_service_code
    
    if [[ "${REMOVE_USER}" == "true" ]]; then
        remove_user_group
    else
        log "Keeping user/group (use --remove-user to delete)"
    fi
    
    if [[ "${PURGE_DATA}" == "true" ]]; then
        purge_data
    else
        log "Keeping service data in ${STATE_DIR} (use --purge-data to delete)"
    fi
    
    log "Uninstall complete."
}

main "$@"
