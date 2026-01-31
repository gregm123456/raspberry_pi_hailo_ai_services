#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-ocr"
SERVICE_USER="hailo-ocr"
SERVICE_GROUP="hailo-ocr"
UNIT_DEST="/etc/systemd/system/hailo-ocr.service"
INSTALL_TARGET="/usr/local/bin/hailo-ocr-server"
ETC_HAILO_CONFIG="/etc/hailo/hailo-ocr.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-ocr"

REMOVE_USER="false"
PURGE_DATA="false"

usage() {
    cat <<'EOF'
Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --remove-user      Remove the service user (default: keep user)
  --purge-data       Remove all service data (default: keep /var/lib/hailo-ocr)
  -h, --help         Show this help
EOF
}

log() {
    echo "[hailo-ocr-uninstall] $*"
}

warn() {
    echo "[hailo-ocr-uninstall] WARNING: $*" >&2
}

error() {
    echo "[hailo-ocr-uninstall] ERROR: $*" >&2
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "This script must be run as root (use: sudo ./uninstall.sh)"
        exit 1
    fi
}

stop_service() {
    log "Stopping service..."
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        systemctl stop "${SERVICE_NAME}.service" || warn "Failed to stop service"
    fi
    
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service"; then
        systemctl disable "${SERVICE_NAME}.service" || warn "Failed to disable service"
    fi
}

remove_unit() {
    log "Removing systemd unit..."
    if [[ -f "${UNIT_DEST}" ]]; then
        rm -f "${UNIT_DEST}"
        systemctl daemon-reload
    fi
}

remove_server_script() {
    log "Removing server script..."
    if [[ -f "${INSTALL_TARGET}" ]]; then
        rm -f "${INSTALL_TARGET}"
    fi
}

remove_config() {
    log "Removing configuration..."
    # Keep user config but remove generated JSON
    if [[ -d "${ETC_XDG_DIR}" ]]; then
        rm -rf "${ETC_XDG_DIR}"
    fi
}

remove_data() {
    if [[ "${PURGE_DATA}" != "true" ]]; then
        return
    fi
    
    log "Purging service data..."
    if [[ -d "/var/lib/hailo-ocr" ]]; then
        rm -rf "/var/lib/hailo-ocr"
    fi
}

remove_user_group() {
    if [[ "${REMOVE_USER}" != "true" ]]; then
        return
    fi
    
    log "Removing service user/group..."
    
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        userdel "${SERVICE_USER}" || warn "Failed to remove user ${SERVICE_USER}"
    fi
    
    if getent group "${SERVICE_GROUP}" >/dev/null; then
        groupdel "${SERVICE_GROUP}" || warn "Failed to remove group ${SERVICE_GROUP}"
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

main() {
    parse_args "$@"
    require_root
    
    log "========================================"
    log "Uninstalling ${SERVICE_NAME} service"
    log "========================================"
    
    stop_service
    remove_unit
    remove_server_script
    remove_config
    remove_data
    remove_user_group
    
    log "Uninstall complete"
    
    if [[ -f "${ETC_HAILO_CONFIG}" ]]; then
        log "User config preserved at ${ETC_HAILO_CONFIG}"
        log "Remove manually if desired: sudo rm ${ETC_HAILO_CONFIG}"
    fi
}

main "$@"
