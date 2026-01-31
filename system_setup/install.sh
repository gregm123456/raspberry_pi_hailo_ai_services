#!/usr/bin/env bash
#
# Hailo-10H System Setup Installer
# Automates OS updates, driver installation, and verification for Raspberry Pi 5 with AI HAT+ 2
#

set -uo pipefail

# Configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LOG_DIR="${SCRIPT_DIR}"
readonly LOG_FILE="${LOG_DIR}/system_setup_install_$(date +%s).log"
readonly CONFIG_FILE="${SCRIPT_DIR}/config.yaml"

# Color output (falls back to plain if not supported)
HAS_COLOR=true
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

if [[ ! -t 1 ]]; then
    HAS_COLOR=false
fi

# ============================================================================
# Logging and Output Functions
# ============================================================================

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] $*" >> "${LOG_FILE}"
}

info() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${BLUE}ℹ${NC} $*"
    else
        echo "• $*"
    fi
    log "INFO: $*"
}

success() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${GREEN}✓${NC} $*"
    else
        echo "[PASS] $*"
    fi
    log "SUCCESS: $*"
}

warning() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${YELLOW}⚠${NC} $*" >&2
    else
        echo "[WARN] $*" >&2
    fi
    log "WARNING: $*"
}

error() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${RED}✗${NC} $*" >&2
    else
        echo "[ERROR] $*" >&2
    fi
    log "ERROR: $*"
}

# ============================================================================
# Validation Functions
# ============================================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use: sudo bash install.sh)"
        exit 1
    fi
    success "Running as root"
}

check_os() {
    if ! grep -q "Trixie" /etc/os-release; then
        error "This script requires Raspberry Pi OS Trixie"
        cat /etc/os-release | grep PRETTY_NAME >&2
        exit 1
    fi
    success "Raspberry Pi OS Trixie detected"
}

check_hardware() {
    # Check if running on Raspberry Pi 5
    if ! grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; then
        warning "System does not appear to be Raspberry Pi 5 (may not be a blocker if model tree is unavailable)"
        log "HARDWARE: $(cat /proc/device-tree/model 2>/dev/null || echo 'unknown')"
    else
        success "Raspberry Pi 5 detected"
    fi
}

check_internet() {
    if ! ping -c 1 8.8.8.8 &> /dev/null; then
        error "No internet connectivity detected. Please ensure your Raspberry Pi has internet access."
        exit 1
    fi
    success "Internet connectivity verified"
}

# ============================================================================
# Installation Functions
# ============================================================================

update_os() {
    info "Updating Raspberry Pi OS and firmware (this may take 5-10 minutes)..."
    
    if ! apt update 2>&1 | tee -a "${LOG_FILE}" | grep -q "packages"; then
        error "Failed to update package lists"
        exit 1
    fi
    
    if ! DEBIAN_FRONTEND=noninteractive apt full-upgrade -y 2>&1 | tee -a "${LOG_FILE}" > /dev/null; then
        error "Failed to upgrade OS packages"
        exit 1
    fi
    success "OS packages upgraded"
    
    info "Updating Raspberry Pi firmware..."
    if ! rpi-eeprom-update -a 2>&1 | tee -a "${LOG_FILE}" > /dev/null; then
        warning "Firmware update encountered an issue (may be non-critical)"
    fi
    success "Firmware update check completed"
}

install_dkms() {
    info "Installing DKMS (Dynamic Kernel Module Support)..."
    
    # Check if already installed
    if dpkg -l | grep -q "^ii.*dkms"; then
        success "DKMS already installed"
        return 0
    fi
    
    if ! DEBIAN_FRONTEND=noninteractive apt install -y dkms 2>&1 | tee -a "${LOG_FILE}" > /dev/null; then
        error "Failed to install DKMS"
        exit 1
    fi
    success "DKMS installed"
}

install_hailo() {
    info "Installing Hailo-10H driver and firmware (hailo-h10-all)..."
    
    # Check if already installed
    if dpkg -l | grep -q "^ii.*hailo-drivers"; then
        success "Hailo packages already installed"
        return 0
    fi
    
    # Remove conflicting packages if present
    if dpkg -l | grep -q "^ii.*hailo-all"; then
        warning "Conflicting hailo-all package found. This will be replaced with hailo-h10-all."
        log "INSTALL: Removing conflicting hailo-all package"
    fi
    
    if ! DEBIAN_FRONTEND=noninteractive apt install -y hailo-h10-all 2>&1 | tee -a "${LOG_FILE}" > /dev/null; then
        error "Failed to install hailo-h10-all package"
        log "INSTALL: Failed packages may be due to repository issues or package conflicts"
        exit 1
    fi
    success "Hailo-10H driver and firmware installed"
}

prompt_reboot() {
    info ""
    info "═══════════════════════════════════════════════════════════"
    info "Installation complete! Reboot required to load kernel module."
    info "═══════════════════════════════════════════════════════════"
    info ""
    
    # Auto-reboot after 10 seconds unless interrupted
    read -t 10 -p "Reboot now? (Y/n, auto-reboots in 10s): " -r choice || choice=""
    choice=${choice:-"y"}
    
    if [[ $choice =~ ^[Yy]$ ]]; then
        info "Rebooting in 5 seconds..."
        sleep 5
        reboot
    else
        warning "Manual reboot required to continue. Run: sudo reboot"
        exit 0
    fi
}

# ============================================================================
# Main
# ============================================================================

main() {
    echo ""
    info "╔══════════════════════════════════════════════════════════╗"
    info "║   Hailo-10H System Setup for Raspberry Pi 5              ║"
    info "║   AI HAT+ 2 Configuration                                ║"
    info "╚══════════════════════════════════════════════════════════╝"
    info ""
    info "Logging to: ${LOG_FILE}"
    info ""
    
    # Validation phase
    info "▶ Validating system prerequisites..."
    check_root
    check_os
    check_hardware
    check_internet
    info "✓ All prerequisites passed"
    info ""
    
    # Installation phase
    info "▶ Installing Hailo-10H system components..."
    update_os
    install_dkms
    install_hailo
    info "✓ All components installed"
    info ""
    
    # Completion
    prompt_reboot
}

# Trap errors
trap 'error "Installation interrupted or failed. Check ${LOG_FILE} for details."; exit 1' ERR

# Run main
main "$@"
