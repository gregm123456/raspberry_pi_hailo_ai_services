#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-clip"
SERVICE_USER="hailo-clip"
SERVICE_GROUP="hailo-clip"
UNIT_DEST="/etc/systemd/system/hailo-clip.service"
ETC_HAILO_CONFIG="/etc/hailo/hailo-clip.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-clip"
STATE_DIR="/var/lib/hailo-clip"
SERVICE_DIR="/opt/hailo-clip"

REMOVE_USER="false"
PURGE_DATA="false"

usage() {
    cat <<'EOF'
Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --remove-user       Delete hailo-clip system user and group
  --purge-data        Delete all data directories (/var/lib/hailo-clip, /etc/xdg/hailo-clip)
  -h, --help          Show this help
EOF
}

log() {
    echo "[hailo-clip-uninstall] $*"
}

warn() {
    echo "[hailo-clip-uninstall] WARNING: $*" >&2
}

error() {
    echo "[hailo-clip-uninstall] ERROR: $*" >&2
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

stop_service() {
    log "Stopping service..."
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        systemctl stop "${SERVICE_NAME}.service"
        log "Service stopped"
    else
        log "Service not running"
    fi
}

disable_service() {
    log "Disabling service..."
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service"; then
        systemctl disable "${SERVICE_NAME}.service"
        log "Service disabled"
    fi
    
    if [[ -f "${UNIT_DEST}" ]]; then
        log "Removing systemd unit: ${UNIT_DEST}"
        rm -f "${UNIT_DEST}"
        systemctl daemon-reload
    fi
}

remove_service_code() {
    log "Removing service code..."
    if [[ -d "${SERVICE_DIR}" ]]; then
        rm -rf "${SERVICE_DIR}"
        log "Removed ${SERVICE_DIR}"
    fi
}

remove_config() {
    log "Removing configuration..."
    if [[ -f "${ETC_HAILO_CONFIG}" ]]; then
        if [[ "${PURGE_DATA}" == "true" ]]; then
            log "Removing config: ${ETC_HAILO_CONFIG}"
            rm -f "${ETC_HAILO_CONFIG}"
        else
            log "Keeping config: ${ETC_HAILO_CONFIG} (use --purge-data to remove)"
        fi
    fi
    
    if [[ -d "${ETC_XDG_DIR}" ]]; then
        if [[ "${PURGE_DATA}" == "true" ]]; then
            log "Removing XDG config dir: ${ETC_XDG_DIR}"
            rm -rf "${ETC_XDG_DIR}"
        else
            log "Keeping XDG config dir: ${ETC_XDG_DIR} (use --purge-data to remove)"
        fi
    fi
}

remove_state() {
    log "Handling state directory..."
    if [[ -d "${STATE_DIR}" ]]; then
        if [[ "${PURGE_DATA}" == "true" ]]; then
            log "Removing state dir: ${STATE_DIR}"
            rm -rf "${STATE_DIR}"
        else
            log "Keeping state dir: ${STATE_DIR} (use --purge-data to remove)"
        fi
    fi
}

remove_user_and_group() {
    if [[ "${REMOVE_USER}" != "true" ]]; then
        return 0
    fi
    
    log "Removing user and group..."
    
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        userdel "${SERVICE_USER}"
        log "Removed user ${SERVICE_USER}"
    fi
    
    if getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
        groupdel "${SERVICE_GROUP}"
        log "Removed group ${SERVICE_GROUP}"
    fi
}

main() {
    parse_args "$@"
    require_root
    
    log "Uninstalling Hailo CLIP Service"
    
    stop_service
    disable_service
    remove_service_code
    remove_config
    remove_state
    remove_user_and_group
    
    log ""
    log "Uninstall complete"
    
    if [[ "${PURGE_DATA}" != "true" ]]; then
        log "To remove all data, run: sudo ./uninstall.sh --purge-data"
    fi
    
    if [[ "${REMOVE_USER}" != "true" ]]; then
        log "To remove system user, run: sudo ./uninstall.sh --remove-user"
    fi
}

main "$@"
