#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-piper"
SERVICE_USER="hailo-piper"
SERVICE_GROUP="hailo-piper"
UNIT_FILE="/etc/systemd/system/hailo-piper.service"
CONFIG_FILE="/etc/hailo/hailo-piper.yaml"
XDG_DIR="/etc/xdg/hailo-piper"
SERVICE_DIR="/opt/hailo-piper"
STATE_DIR="/var/lib/hailo-piper"

log() {
    echo "[uninstall] $*"
}

warn() {
    echo "[uninstall] WARNING: $*" >&2
}

error() {
    echo "[uninstall] ERROR: $*" >&2
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "This script must be run as root (use: sudo ./uninstall.sh)"
        exit 1
    fi
}

confirm_uninstall() {
    echo "This will remove the Hailo Piper TTS service, including:"
    echo "  - systemd service"
    echo "  - Service user and group"
    echo "  - Configuration files"
    echo "  - State directory (models and cache)"
    echo ""
    read -p "Continue? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Uninstall cancelled"
        exit 0
    fi
}

stop_and_disable_service() {
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        log "Stopping service..."
        systemctl stop "${SERVICE_NAME}.service"
    fi
    
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        log "Disabling service..."
        systemctl disable "${SERVICE_NAME}.service"
    fi
}

remove_systemd_unit() {
    if [[ -f "${UNIT_FILE}" ]]; then
        log "Removing systemd unit file..."
        rm -f "${UNIT_FILE}"
        systemctl daemon-reload
    fi
}

remove_files() {
    log "Removing service files..."
    
    [[ -d "${SERVICE_DIR}" ]] && rm -rf "${SERVICE_DIR}"
    [[ -d "${XDG_DIR}" ]] && rm -rf "${XDG_DIR}"
    
    # Ask before removing config (may contain customizations)
    if [[ -f "${CONFIG_FILE}" ]]; then
        read -p "Remove config file ${CONFIG_FILE}? [y/N] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "${CONFIG_FILE}"
        fi
    fi
    
    # Ask before removing state dir (contains downloaded models)
    if [[ -d "${STATE_DIR}" ]]; then
        read -p "Remove state directory ${STATE_DIR}? (includes models) [y/N] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "${STATE_DIR}"
        else
            warn "Keeping ${STATE_DIR}"
        fi
    fi
}

remove_user() {
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Removing service user..."
        userdel "${SERVICE_USER}" 2>/dev/null || warn "Failed to remove user ${SERVICE_USER}"
    fi
    
    if getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
        log "Removing service group..."
        groupdel "${SERVICE_GROUP}" 2>/dev/null || warn "Failed to remove group ${SERVICE_GROUP}"
    fi
}

main() {
    require_root
    confirm_uninstall
    
    stop_and_disable_service
    remove_systemd_unit
    remove_files
    remove_user
    
    log "Uninstall complete"
}

main "$@"
