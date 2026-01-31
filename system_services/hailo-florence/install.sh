#!/bin/bash
# hailo-florence Installation Script
# Installs Florence-2 image captioning service for Raspberry Pi 5 + Hailo-10H

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="hailo-florence"
SERVICE_USER="hailo-florence"
SERVICE_GROUP="hailo-florence"
SERVICE_DIR="/opt/hailo/florence"
CONFIG_DIR="/etc/hailo/florence"
LOG_DIR="/opt/hailo/florence/logs"
MODEL_DIR="/opt/hailo/florence/models"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging functions
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
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Hailo driver
    if ! command -v hailortcli &> /dev/null; then
        log_error "Hailo driver not found. Please install hailo-h10-all package."
        log_error "See: reference_documentation/system_setup.md"
        exit 1
    fi
    
    # Verify Hailo device
    if ! hailortcli fw-control identify &> /dev/null; then
        log_error "Hailo device not accessible. Please check driver installation."
        exit 1
    fi
    
    log_info "Hailo device detected: $(hailortcli fw-control identify | grep 'Device Architecture' | awk '{print $3}')"
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 not found"
        exit 1
    fi
    
    python_version=$(python3 --version | awk '{print $2}')
    log_info "Python version: $python_version"
    
    # Check available memory
    available_mem=$(free -g | awk '/^Mem:/{print $7}')
    if [ "$available_mem" -lt 4 ]; then
        log_warn "Low available memory: ${available_mem}GB (recommended: 4GB+)"
        log_warn "Consider stopping other services before continuing"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_info "Prerequisites check: OK"
}

# Create system user
create_user() {
    log_info "Creating service user: $SERVICE_USER"
    
    if id "$SERVICE_USER" &>/dev/null; then
        log_warn "User $SERVICE_USER already exists, skipping"
    else
        useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
        log_info "User $SERVICE_USER created"
    fi
    
    # Add to video group for Hailo device access
    usermod -a -G video "$SERVICE_USER"
}

# Create directories
create_directories() {
    log_info "Creating service directories..."
    
    mkdir -p "$SERVICE_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$MODEL_DIR"
    
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$SERVICE_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
    chmod 755 "$SERVICE_DIR"
    chmod 755 "$CONFIG_DIR"
    chmod 755 "$LOG_DIR"
    
    log_info "Directories created"
}

# Install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # System packages
    apt-get update
    apt-get install -y \
        python3-pip \
        python3-opencv \
        python3-yaml \
        libonnxruntime-dev || true
    
    # Python packages
    pip3 install --break-system-packages \
        fastapi \
        uvicorn[standard] \
        pillow \
        transformers \
        onnxruntime \
        pyyaml \
        aiofiles || {
        log_warn "Some packages may have failed to install"
        log_warn "This is expected if packages are already present"
    }
    
    log_info "Dependencies installed"
}

# Copy service implementation
copy_implementation() {
    log_info "Copying service implementation..."
    
    # Check if hailo-rpi5-examples exists
    RPI5_EXAMPLES_DIR="$(dirname "$SCRIPT_DIR")/hailo-rpi5-examples/community_projects/dynamic_captioning"
    
    if [ ! -d "$RPI5_EXAMPLES_DIR" ]; then
        log_error "hailo-rpi5-examples not found at: $RPI5_EXAMPLES_DIR"
        log_error "Please ensure the repository is properly initialized"
        exit 1
    fi
    
    # Copy base implementation
    cp -r "$RPI5_EXAMPLES_DIR"/* "$SERVICE_DIR/" || {
        log_error "Failed to copy implementation files"
        exit 1
    }
    
    # Copy server.py from this directory if it exists
    if [ -f "$SCRIPT_DIR/server.py" ]; then
        cp "$SCRIPT_DIR/server.py" "$SERVICE_DIR/"
    fi
    
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$SERVICE_DIR"
    
    log_info "Implementation copied"
}

# Download model files
download_models() {
    log_info "Checking model files..."
    
    # Model download will be handled by the service on first run
    # or we can download them now if URLs are available
    
    log_warn "Model files will be downloaded on first service start"
    log_warn "This may take several minutes and require internet connectivity"
    
    # TODO: Add explicit model download if we have direct URLs
    # For now, rely on the existing implementation's download mechanism
}

# Render and install configuration
install_config() {
    log_info "Installing configuration..."
    
    # Render config with defaults
    python3 "$SCRIPT_DIR/render_config.py" \
        --template "$SCRIPT_DIR/config.yaml" \
        --output "$CONFIG_DIR/config.yaml"
    
    chmod 644 "$CONFIG_DIR/config.yaml"
    
    log_info "Configuration installed: $CONFIG_DIR/config.yaml"
}

# Install systemd service
install_systemd_service() {
    log_info "Installing systemd service..."
    
    cp "$SCRIPT_DIR/$SERVICE_NAME.service" "/etc/systemd/system/"
    chmod 644 "/etc/systemd/system/$SERVICE_NAME.service"
    
    systemctl daemon-reload
    
    log_info "systemd service installed"
}

# Enable and start service
enable_service() {
    log_info "Enabling service..."
    
    systemctl enable "$SERVICE_NAME"
    
    log_info "Starting service (this may take 60-120 seconds for model loading)..."
    systemctl start "$SERVICE_NAME"
    
    # Wait for service to become ready
    log_info "Waiting for service to initialize..."
    for i in {1..30}; do
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            log_info "Service started successfully"
            return 0
        fi
        sleep 2
        echo -n "."
    done
    
    echo ""
    log_warn "Service may still be initializing. Check status with:"
    log_warn "  sudo systemctl status $SERVICE_NAME"
    log_warn "  sudo journalctl -u $SERVICE_NAME -f"
}

# Show post-installation info
show_info() {
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "hailo-florence installation complete!"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Service Status:"
    echo "  sudo systemctl status $SERVICE_NAME"
    echo ""
    echo "View Logs:"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "Test API:"
    echo "  curl http://localhost:8082/health"
    echo ""
    echo "Run Verification:"
    echo "  cd $SCRIPT_DIR && ./verify.sh"
    echo ""
    echo "Configuration:"
    echo "  $CONFIG_DIR/config.yaml"
    echo ""
    echo "Documentation:"
    echo "  README.md - Overview and usage"
    echo "  API_SPEC.md - API documentation"
    echo "  TROUBLESHOOTING.md - Common issues"
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Main installation flow
main() {
    log_info "Starting hailo-florence installation..."
    echo ""
    
    check_root
    check_prerequisites
    create_user
    create_directories
    install_dependencies
    copy_implementation
    download_models
    install_config
    install_systemd_service
    enable_service
    show_info
}

main "$@"
