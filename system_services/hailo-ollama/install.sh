#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-ollama"
SERVICE_USER="hailo-ollama"
SERVICE_GROUP="hailo-ollama"
UNIT_SRC="${SCRIPT_DIR}/hailo-ollama.service"
UNIT_DEST="/etc/systemd/system/hailo-ollama.service"
CONFIG_TEMPLATE="${SCRIPT_DIR}/config.yaml"
ETC_HAILO_CONFIG="/etc/hailo/hailo-ollama.yaml"
ETC_XDG_DIR="/etc/xdg/hailo-ollama"
JSON_CONFIG="${ETC_XDG_DIR}/hailo-ollama.json"
RENDER_SCRIPT="${SCRIPT_DIR}/render_config.py"
DEFAULT_PORT="11434"

WARMUP_PULL=""
WARMUP_CHAT=""

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --warmup-pull MODEL    Pull a model after install (optional)
  --warmup-chat MODEL    Run a short /api/chat warmup (optional)
  -h, --help             Show this help
EOF
}

log() {
    echo "[hailo-ollama] $*"
}

warn() {
    echo "[hailo-ollama] WARNING: $*" >&2
}

error() {
    echo "[hailo-ollama] ERROR: $*" >&2
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

check_python_yaml() {
    require_command python3 "Install with: sudo apt install python3"
    if ! python3 - <<'PY' >/dev/null 2>&1
import yaml
PY
    then
        error "PyYAML is required. Install with: sudo apt install python3-yaml"
        exit 1
    fi
}

preflight_hailo() {
    if [[ ! -e /dev/hailo0 ]]; then
        error "/dev/hailo0 not found. Install Hailo driver: sudo apt install dkms hailo-h10-all"
        exit 1
    fi

    if command -v hailortcli >/dev/null 2>&1; then
        if ! hailortcli fw-control identify >/dev/null 2>&1; then
            warn "hailortcli verification failed. Hailo device may not be ready."
        fi
    else
        warn "hailortcli not found; skipping firmware verification."
    fi
}

preflight_hailo_ollama() {
    if ! command -v hailo-ollama >/dev/null 2>&1; then
        error "hailo-ollama not found in PATH. Install the Developer Zone Debian package first."
        exit 1
    fi
}

create_user_group() {
    if ! getent group "${SERVICE_GROUP}" >/dev/null; then
        log "Creating system group ${SERVICE_GROUP}"
        groupadd --system "${SERVICE_GROUP}"
    fi

    if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Creating system user ${SERVICE_USER}"
        useradd -r -s /usr/sbin/nologin -d /var/lib/hailo-ollama -g "${SERVICE_GROUP}" "${SERVICE_USER}"
    fi
}

configure_device_permissions() {
    local device_group
    device_group=$(stat -c '%G' /dev/hailo0)

    if [[ -z "${device_group}" ]]; then
        error "Could not determine group for /dev/hailo0"
        exit 1
    fi

    if ! getent group "${device_group}" >/dev/null; then
        error "Device group '${device_group}' not found. Check Hailo installation/udev rules."
        exit 1
    fi

    log "Adding ${SERVICE_USER} to ${device_group} group"
    usermod -aG "${device_group}" "${SERVICE_USER}"
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
    python3 "${RENDER_SCRIPT}" --input "${ETC_HAILO_CONFIG}" --output "${JSON_CONFIG}"
}

get_config_port() {
    python3 - <<'PY' 2>/dev/null || echo "${DEFAULT_PORT}"
import yaml
import sys

path = "/etc/hailo/hailo-ollama.yaml"
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    server = data.get("server", {}) if isinstance(data, dict) else {}
    port = server.get("port", 11434)
    print(int(port))
except Exception:
    print(11434)
PY
}

warn_if_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
            warn "Port ${port} is already in use. Update /etc/hailo/hailo-ollama.yaml if needed."
        fi
    fi
}

install_unit() {
    log "Installing systemd unit to ${UNIT_DEST}"
    install -m 0644 "${UNIT_SRC}" "${UNIT_DEST}"

    systemctl daemon-reload
    systemctl enable --now "${SERVICE_NAME}.service"
}

verify_service() {
    local port="$1"

    if ! systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        error "Service failed to start. Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
        return 1
    fi

    if command -v curl >/dev/null 2>&1; then
        local attempt
        for attempt in {1..5}; do
            if curl -fsS "http://localhost:${port}/api/version" >/dev/null 2>&1; then
                log "Health check succeeded on port ${port}"
                return 0
            fi
            sleep 1
        done
        warn "Health check failed at http://localhost:${port}/api/version"
        warn "Check logs: journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
    else
        warn "curl not found; skipping HTTP health check"
    fi
}

warmup_pull() {
    local port="$1"
    local model="$2"
    log "Warmup: pulling model ${model}"
    curl -fsS -X POST "http://localhost:${port}/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${model}\"}" >/dev/null
}

warmup_chat() {
    local port="$1"
    local model="$2"
    log "Warmup: running /api/chat with model ${model}"
    curl -fsS -X POST "http://localhost:${port}/api/chat" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"${model}\", \"messages\": [{\"role\": \"user\", \"content\": \"hello\"}], \"stream\": false}" \
        >/dev/null
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --warmup-pull)
                WARMUP_PULL="$2"
                shift 2
                ;;
            --warmup-chat)
                WARMUP_CHAT="$2"
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
    parse_args "$@"
    require_root
    preflight_hailo
    preflight_hailo_ollama
    check_python_yaml

    create_user_group
    configure_device_permissions
    install_config

    local port
    port="$(get_config_port)"
    warn_if_port_in_use "${port}"

    install_unit
    verify_service "${port}"

    if [[ -n "${WARMUP_PULL}" ]]; then
        warmup_pull "${port}" "${WARMUP_PULL}" || warn "Warmup pull failed"
    fi

    if [[ -n "${WARMUP_CHAT}" ]]; then
        warmup_chat "${port}" "${WARMUP_CHAT}" || warn "Warmup chat failed"
    fi

    log "Install complete. Config: ${ETC_HAILO_CONFIG}"
}

main "$@"
