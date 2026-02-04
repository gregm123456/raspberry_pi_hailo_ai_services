#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-whisper"
SERVICE_USER="hailo-whisper"
SERVICE_GROUP="hailo-whisper"

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

stop_and_disable() {
    log "Stopping and disabling service"
    
    if systemctl is-active "${SERVICE_NAME}.service" >/dev/null 2>&1; then
        systemctl stop "${SERVICE_NAME}.service"
    fi
    
    if systemctl is-enabled "${SERVICE_NAME}.service" >/dev/null 2>&1; then
        systemctl disable "${SERVICE_NAME}.service"
    fi
}

remove_unit() {
    log "Removing systemd unit"
    
    local unit_path="/etc/systemd/system/${SERVICE_NAME}.service"
    if [[ -f "${unit_path}" ]]; then
        rm -f "${unit_path}"
    fi
    
    systemctl daemon-reload
}

remove_service_dir() {
    log "Removing /opt service directory"

    if [[ -d /opt/hailo-whisper ]]; then
        rm -rf /opt/hailo-whisper
    fi
}

remove_config() {
    log "Removing configuration files"
    
    if [[ -d /etc/xdg/hailo-whisper ]]; then
        rm -rf /etc/xdg/hailo-whisper
    fi
    
    # Keep /etc/hailo/hailo-whisper.yaml (user may have customized)
    if [[ -f /etc/hailo/hailo-whisper.yaml ]]; then
        warn "Keeping user config at /etc/hailo/hailo-whisper.yaml (remove manually if desired)"
    fi
}

remove_state() {
    log "Removing state directory"
    
    if [[ -d /var/lib/hailo-whisper ]]; then
        warn "Removing /var/lib/hailo-whisper (including cached audio files)"
        rm -rf /var/lib/hailo-whisper
    fi
}

remove_user() {
    log "Removing service user and group"
    
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        userdel "${SERVICE_USER}" 2>/dev/null || warn "Failed to remove user ${SERVICE_USER}"
    fi
    
    if getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
        groupdel "${SERVICE_GROUP}" 2>/dev/null || warn "Failed to remove group ${SERVICE_GROUP}"
    fi
}

main() {
    require_root
    
    log "Uninstalling hailo-whisper service"
    
    stop_and_disable
    remove_unit
    remove_service_dir
    remove_config
    remove_state
    remove_user
    
    log "Uninstall complete"
}

main "$@"
