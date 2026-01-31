#!/usr/bin/env bash
set -euo pipefail

# Hailo Face Recognition Service Uninstaller

SERVICE_NAME="hailo-face"
SERVICE_USER="hailo-face"
INSTALL_DIR="/opt/${SERVICE_NAME}"
CONFIG_FILE="/etc/hailo/${SERVICE_NAME}.yaml"
STATE_DIR="/var/lib/${SERVICE_NAME}"
LOG_DIR="/var/log/${SERVICE_NAME}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
    fi
}

confirm_uninstall() {
    warn "This will remove the ${SERVICE_NAME} service and delete all data"
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Uninstall cancelled"
        exit 0
    fi
}

stop_service() {
    info "Stopping ${SERVICE_NAME} service..."
    
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        systemctl stop "${SERVICE_NAME}.service" || warn "Failed to stop service"
    else
        info "Service already stopped"
    fi
}

disable_service() {
    info "Disabling ${SERVICE_NAME} service..."
    
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
        systemctl disable "${SERVICE_NAME}.service" || warn "Failed to disable service"
    else
        info "Service not enabled"
    fi
}

remove_systemd_unit() {
    info "Removing systemd unit..."
    
    if [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]; then
        rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
        info "Systemd unit removed"
    fi
}

remove_files() {
    info "Removing service files..."
    
    [[ -d "${INSTALL_DIR}" ]] && rm -rf "${INSTALL_DIR}" && info "Removed ${INSTALL_DIR}"
    [[ -d "${LOG_DIR}" ]] && rm -rf "${LOG_DIR}" && info "Removed ${LOG_DIR}"
    
    # Ask about data directory (contains face database)
    if [[ -d "${STATE_DIR}" ]]; then
        warn "Database directory: ${STATE_DIR}"
        read -p "Delete face database? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "${STATE_DIR}"
            info "Removed ${STATE_DIR}"
        else
            info "Preserved ${STATE_DIR}"
        fi
    fi
    
    # Ask about config
    if [[ -f "${CONFIG_FILE}" ]]; then
        read -p "Delete config file? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "${CONFIG_FILE}"
            info "Removed ${CONFIG_FILE}"
        else
            info "Preserved ${CONFIG_FILE}"
        fi
    fi
}

remove_user() {
    info "Removing service user..."
    
    if id "${SERVICE_USER}" &>/dev/null; then
        userdel "${SERVICE_USER}" || warn "Failed to remove user"
        info "User removed"
    else
        info "User does not exist"
    fi
}

main() {
    info "Uninstalling Hailo Face Recognition Service..."
    
    check_root
    confirm_uninstall
    stop_service
    disable_service
    remove_systemd_unit
    remove_files
    remove_user
    
    info "Uninstall complete!"
}

main "$@"
