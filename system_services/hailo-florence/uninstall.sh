#!/bin/bash
# hailo-florence Uninstallation Script
# Removes the Florence-2 image captioning service

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICE_NAME="hailo-florence"
SERVICE_USER="hailo-florence"
SERVICE_DIR="/opt/hailo/florence"
CONFIG_DIR="/etc/hailo/florence"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Uninstalling hailo-florence service..."

# Stop service
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_info "Stopping service..."
    systemctl stop "$SERVICE_NAME"
fi

# Disable service
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    log_info "Disabling service..."
    systemctl disable "$SERVICE_NAME"
fi

# Remove systemd unit
if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    log_info "Removing systemd unit..."
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
fi

# Remove service directory
if [ -d "$SERVICE_DIR" ]; then
    log_info "Removing service directory: $SERVICE_DIR"
    rm -rf "$SERVICE_DIR"
fi

# Remove config directory
if [ -d "$CONFIG_DIR" ]; then
    log_info "Removing config directory: $CONFIG_DIR"
    rm -rf "$CONFIG_DIR"
fi

# Remove user
if id "$SERVICE_USER" &>/dev/null; then
    log_info "Removing service user: $SERVICE_USER"
    userdel -r "$SERVICE_USER" 2>/dev/null || true
fi

log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "hailo-florence uninstallation complete!"
log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
