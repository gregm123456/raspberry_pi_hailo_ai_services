#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-piper"
SERVICE_USER="hailo-piper"
SERVICE_GROUP="hailo-piper"
UNIT_SRC="${SCRIPT_DIR}/hailo-piper.service"
UNIT_DEST="/etc/systemd/system/hailo-piper.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-piper.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-piper"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-piper.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="5003"
SERVICE_DIR="/opt/hailo-piper"
MODEL_DIR="/var/lib/hailo-piper/models"
DEFAULT_MODEL="en_US-lessac-medium"
REQUIREMENTS_SRC="${SCRIPT_DIR}/requirements.txt"
PYTHON_BIN="python3"

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --download-model  Download the default Piper TTS model
    --model NAME      Specify model name (default: en_US-lessac-medium)
    --model-url URL   Full model URL (used for non-default voices)
  -h, --help        Show this help
EOF
}

log() {
    echo "[hailo-piper] $*"
}

warn() {
    echo "[hailo-piper] WARNING: $*" >&2
}

error() {
    echo "[hailo-piper] ERROR: $*" >&2
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "This script must be run as root (use: sudo ./install.sh)"
        exit 1
    fi
}

require_command() {
    local cmd="$1"
    local hint="$2"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        error "Missing required command: ${cmd}. ${hint}"
        exit 1
    fi
}

check_python_requirements() {
    require_command "${PYTHON_BIN}" "Install with: sudo apt install python3 python3-venv"
    if ! "${PYTHON_BIN}" -m venv --help >/dev/null 2>&1; then
        error "${PYTHON_BIN}-venv is required. Install with: sudo apt install python3-venv"
        exit 1
    fi
}

check_build_tools() {
    log "Checking for build tools required to compile piper-phonemize..."
    
    if ! command -v gcc >/dev/null 2>&1; then
        error "gcc not found. Install with: sudo apt install build-essential python3-dev"
        exit 1
    fi
    
    log "✓ Build tools available"
}

create_user_group() {
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Creating system group ${SERVICE_GROUP}"
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Creating system user ${SERVICE_USER}"
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-piper -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
}

create_state_directories() {
    log "Creating service directories"
    mkdir -p /var/lib/hailo-piper/{models,cache}
    mkdir -p /opt/hailo-piper

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-piper
    chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-piper

    # Copy service code if available
    if [[ -f "${SCRIPT_DIR}/hailo_piper_service.py" ]]; then
        cp "${SCRIPT_DIR}/hailo_piper_service.py" "${SERVICE_DIR}/"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/hailo_piper_service.py"
        chmod 0755 "${SERVICE_DIR}/hailo_piper_service.py"
    fi

    if [[ -f "${REQUIREMENTS_SRC}" ]]; then
        cp "${REQUIREMENTS_SRC}" "${SERVICE_DIR}/"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/requirements.txt"
    fi
}

create_venv() {
    log "Creating Python virtual environment (isolated, no system site packages)"
    rm -rf "${SERVICE_DIR}/venv"
    "${PYTHON_BIN}" -m venv "${SERVICE_DIR}/venv"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_DIR}/venv"
}

install_requirements() {
    if [[ ! -f "${SERVICE_DIR}/requirements.txt" ]]; then
        error "requirements.txt not found in ${SERVICE_DIR}"
        exit 1
    fi

    log "Installing Python requirements in venv (this may take 2-5 minutes; piper-phonemize builds from source)"
    "${SERVICE_DIR}/venv/bin/pip" install --upgrade pip setuptools wheel
    
    # Install with --no-cache-dir to save space and force fresh build
    if ! "${SERVICE_DIR}/venv/bin/pip" install --no-cache-dir -r "${SERVICE_DIR}/requirements.txt"; then
        error "Failed to install requirements. Check logs above."
        error "Common issues:"
        error "  - piper-phonemize build failure: ensure gcc, make, python3-dev are installed"
        error "    Fix: sudo apt install build-essential python3-dev"
        exit 1
    fi
}

download_piper_model() {
    local model_name="$1"
    local model_url=""
    local json_url=""
    
    log "Downloading Piper TTS model: ${model_name}"

    if [[ -n "${MODEL_URL:-}" ]]; then
        model_url="${MODEL_URL}"
    elif [[ "${model_name}" == "${DEFAULT_MODEL}" ]]; then
        model_url="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/${model_name}.onnx?download=true"
    else
        error "Model URL not specified for ${model_name}. Use --model-url to provide a full URL."
        return 1
    fi

    if [[ "${model_url}" == *".onnx?"* ]]; then
        json_url="${model_url/.onnx?/.onnx.json?}"
    elif [[ "${model_url}" == *".onnx" ]]; then
        json_url="${model_url/.onnx/.onnx.json}"
    else
        json_url="${model_url}.json"
    fi
    
    if [[ -f "${MODEL_DIR}/${model_name}.onnx" ]]; then
        log "Model already exists at ${MODEL_DIR}/${model_name}.onnx"
        return 0
    fi
    
    if ! command -v wget >/dev/null 2>&1; then
        error "wget not found. Install with: sudo apt install wget"
        return 1
    fi
    
    mkdir -p "${MODEL_DIR}"
    cd "${MODEL_DIR}"
    
    log "Downloading ${model_name}.onnx..."
    if ! wget -q --show-progress "${model_url}" -O "${model_name}.onnx"; then
        error "Failed to download model. Check URL: ${model_url}"
        return 1
    fi
    
    log "Downloading ${model_name}.onnx.json..."
    if ! wget -q --show-progress "${json_url}" -O "${model_name}.onnx.json"; then
        error "Failed to download model config. Check URL: ${json_url}"
        return 1
    fi
    
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "${MODEL_DIR}/${model_name}.onnx" "${MODEL_DIR}/${model_name}.onnx.json"
    log "Model downloaded successfully"
    return 0
}

install_config() {
    install -d -m 0755 /etc/hailo
    if [[ ! -f "${ETC_HAILO_CONFIG}" ]]; then
        log "Installing default config to ${ETC_HAILO_CONFIG}"
        install -m 0644 "${CONFIG_TEMPLATE}" "${ETC_HAILO_CONFIG}"
    else
        log "Config already exists at ${ETC_HAILO_CONFIG} (leaving unchanged)"
    fi

    install -d -m 0755 "${ETC_XDG_DIR}"
    log "Rendering JSON config to ${JSON_CONFIG}"
    "${SERVICE_DIR}/venv/bin/python3" "${RENDER_SCRIPT}" --input "${ETC_HAILO_CONFIG}" --output "${JSON_CONFIG}"
}

get_config_port() {
    "${SERVICE_DIR}/venv/bin/python3" - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
import sys

path = "/etc/hailo/hailo-piper.yaml"
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    server = data.get("server", {}) if isinstance(data, dict) else {}
    port = server.get("port", 5003)
    print(int(port))
except Exception:
    print(5003)
PY
}

warn_if_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-piper.yaml if needed."
        fi
    fi
}

install_unit() {
    log "Installing systemd unit to ${UNIT_DEST}"
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"

    systemctl daemon-reload
    systemctl enable --now "${SERVICE_NAME}.service"
    systemctl restart "${SERVICE_NAME}.service"
}

verify_service() {
    local port="$1"

    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service failed to start. Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
        return 1
    fi

    if command -v curl >/dev/null 2>&1; then
        local attempt
        for attempt in {1..10}; do
            if curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1; then
                log "Health check succeeded on port ${port}"
                return 0
            fi
            sleep 1
        done
        warn "Health check failed at http://localhost:${port}/health"
        warn "Service may still be initializing. Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
    else
        warn "curl not found; skipping HTTP health check"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --download-model)
                DOWNLOAD_MODEL="true"
                shift
                ;;
            --model)
                MODEL_NAME="$2"
                shift 2
                ;;
            --model-url)
                MODEL_URL="$2"
                shift 2
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
    local DOWNLOAD_MODEL="false"
    local MODEL_NAME="${DEFAULT_MODEL}"
    local MODEL_URL=""
    parse_args "$@"

    require_root
    check_python_requirements
    check_build_tools

    create_user_group
    create_state_directories
    create_venv
    install_requirements
    
    # Download model if requested
    if [[ "${DOWNLOAD_MODEL}" == "true" ]]; then
        if ! download_piper_model "${MODEL_NAME}"; then
            error "Failed to download model. You can manually download from:"
            error "  https://github.com/rhasspy/piper/releases"
            exit 1
        fi
    else
        # Check if model exists
        if [[ ! -f "${MODEL_DIR}/${DEFAULT_MODEL}.onnx" ]]; then
            warn "Piper TTS model not found at ${MODEL_DIR}/${DEFAULT_MODEL}.onnx"
            warn "Run with --download-model to automatically download, or manually place model files in ${MODEL_DIR}"
        fi
    fi
    
    install_config

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
    log "Service: systemctl status hailo-piper.service"
    log "Logs: journalctl -u hailo-piper.service -f"
    log ""
    log "Test synthesis:"
    log "  curl -X POST http://localhost:${port}/v1/audio/speech \\"
    log "    -H 'Content-Type: application/json' \\"
    log "    -d '{\"input\": \"Hello from Hailo Piper TTS\"}' \\"
    log "    --output speech.wav"
}

main "$@"
