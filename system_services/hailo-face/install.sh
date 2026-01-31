#!/usr/bin/env bash
set -euo pipefail

# Hailo Face Recognition Service Installer
# Installs and configures hailo-face as a systemd service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-face"
SERVICE_USER="hailo-face"
SERVICE_GROUP="hailo-face"
INSTALL_DIR="/opt/${SERVICE_NAME}"
CONFIG_DIR="/etc/hailo"
CONFIG_FILE="${CONFIG_DIR}/${SERVICE_NAME}.yaml"
STATE_DIR="/var/lib/${SERVICE_NAME}"
LOG_DIR="/var/log/${SERVICE_NAME}"
DB_DIR="${STATE_DIR}/database"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

check_prerequisites() {
    info "Checking prerequisites..."
    
    # Check for Hailo driver
    if ! lsmod | grep -q hailo; then
        warn "Hailo kernel module not loaded"
        warn "Run: sudo apt install dkms hailo-h10-all && sudo reboot"
    fi
    
    # Check for Python
    if ! command -v python3 &> /dev/null; then
        error "Python 3 not found. Install with: sudo apt install python3"
    fi
    
    # Check for required Python packages
    local missing_packages=()
    for pkg in flask pyyaml opencv-python pillow numpy; do
        if ! python3 -c "import ${pkg//-/_}" 2>/dev/null; then
            missing_packages+=("$pkg")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        info "Installing missing Python packages: ${missing_packages[*]}"
        python3 -m pip install --break-system-packages "${missing_packages[@]}" || \
            error "Failed to install Python packages"
    fi
    
    info "Prerequisites OK"
}

create_user() {
    info "Creating service user: ${SERVICE_USER}"
    
    if id "${SERVICE_USER}" &>/dev/null; then
        info "User ${SERVICE_USER} already exists"
    else
        useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}" || \
            error "Failed to create user"
    fi
    
    # Add to video group for Hailo device access
    usermod -a -G video "${SERVICE_USER}" || warn "Failed to add user to video group"
}

install_service_files() {
    info "Installing service files..."
    
    # Create directories
    mkdir -p "${INSTALL_DIR}"
    mkdir -p "${CONFIG_DIR}"
    mkdir -p "${STATE_DIR}"
    mkdir -p "${DB_DIR}"
    mkdir -p "${LOG_DIR}"
    
    # Copy service script
    cp "${SCRIPT_DIR}/hailo_face_service.py" "${INSTALL_DIR}/" || \
        error "Failed to copy service script"
    chmod +x "${INSTALL_DIR}/hailo_face_service.py"
    
    # Render and install config
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        info "Rendering configuration..."
        python3 "${SCRIPT_DIR}/render_config.py" "${CONFIG_FILE}" || \
            error "Failed to render config"
    else
        info "Config already exists: ${CONFIG_FILE}"
        info "To regenerate, delete it and re-run installer"
    fi
    
    # Set permissions
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${STATE_DIR}"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${LOG_DIR}"
    chmod 755 "${INSTALL_DIR}"
    chmod 644 "${CONFIG_FILE}"
    chmod 755 "${STATE_DIR}"
    chmod 755 "${DB_DIR}"
    
    info "Service files installed"
}

install_systemd_unit() {
    info "Installing systemd unit..."
    
    cp "${SCRIPT_DIR}/${SERVICE_NAME}.service" "/etc/systemd/system/" || \
        error "Failed to copy systemd unit"
    
    systemctl daemon-reload || error "Failed to reload systemd"
    
    info "Systemd unit installed"
}

enable_service() {
    info "Enabling ${SERVICE_NAME} service..."
    
    systemctl enable "${SERVICE_NAME}.service" || \
        error "Failed to enable service"
    
    info "Service enabled"
}

start_service() {
    info "Starting ${SERVICE_NAME} service..."
    
    systemctl start "${SERVICE_NAME}.service" || \
        error "Failed to start service"
    
    sleep 2
    
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        info "Service started successfully"
    else
        error "Service failed to start. Check: journalctl -u ${SERVICE_NAME} -n 50"
    fi
}

show_status() {
    info "Service status:"
    systemctl status "${SERVICE_NAME}.service" --no-pager || true
    
    echo ""
    info "Useful commands:"
    echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
    echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
    echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
    echo ""
    info "API endpoints:"
    echo "  Health:     GET  http://localhost:5002/health"
    echo "  Detect:     POST http://localhost:5002/v1/detect"
    echo "  Embed:      POST http://localhost:5002/v1/embed"
    echo "  Recognize:  POST http://localhost:5002/v1/recognize"
    echo "  Add ID:     POST http://localhost:5002/v1/database/add"
    echo "  Remove ID:  POST http://localhost:5002/v1/database/remove"
    echo "  List IDs:   GET  http://localhost:5002/v1/database/list"
    echo ""
    info "Configuration: ${CONFIG_FILE}"
    info "Database:      ${STATE_DIR}/faces.db"
}

main() {
    info "Installing Hailo Face Recognition Service..."
    
    check_root
    check_prerequisites
    create_user
    install_service_files
    install_systemd_unit
    enable_service
    start_service
    show_status
    
    info "Installation complete!"
}

main "$@"
