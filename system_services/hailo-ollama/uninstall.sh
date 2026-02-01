#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hailo-ollama"
SERVICE_USER="hailo-ollama"
SERVICE_GROUP="hailo-ollama"
UNIT_DEST="/etc/systemd/system/hailo-ollama.service"
STATE_DIR="/var/lib/hailo-ollama"

PURGE_DATA=false
REMOVE_USER=false

usage() {
    cat <<'EOF'
Usage: sudo ./uninstall.sh [OPTIONS]

Options:
  --purge-data    Remove /var/lib/hailo-ollama (model storage)
  --remove-user   Remove the hailo-ollama user and group
  -h, --help      Show this help
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
        error "This script must be run as root (use: sudo ./uninstall.sh)"
        exit 1
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --purge-data)
                PURGE_DATA=true
                shift
                ;;
            --remove-user)
                REMOVE_USER=true
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

remove_unit() {
    if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
        systemctl disable --now "${SERVICE_NAME}.service" || true
    fi

    if [[ -f "${UNIT_DEST}" ]]; then
        rm -f "${UNIT_DEST}"
        systemctl daemon-reload
    fi

    # Remove monitoring drop-in if present
    if [[ -d "/etc/systemd/system/${SERVICE_NAME}.service.d" ]]; then
        rm -f /etc/systemd/system/${SERVICE_NAME}.service.d/monitor.conf || true
        rmdir --ignore-fail-on-non-empty /etc/systemd/system/${SERVICE_NAME}.service.d || true
        systemctl daemon-reload || true
    fi
}

remove_user_group() {
    if [[ "${REMOVE_USER}" != true ]]; then
        return
    fi

    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        userdel "${SERVICE_USER}" || warn "Failed to remove user ${SERVICE_USER}"
    fi

    if getent group "${SERVICE_GROUP}" >/dev/null; then
        local members
        members=$(getent group "${SERVICE_GROUP}" | awk -F: '{print $4}')
        if [[ -z "${members}" ]]; then
            groupdel "${SERVICE_GROUP}" || warn "Failed to remove group ${SERVICE_GROUP}"
        else
            warn "Group ${SERVICE_GROUP} has members (${members}); not removing"
        fi
    fi
}

purge_data() {
    if [[ "${PURGE_DATA}" == true ]]; then
        log "Removing ${STATE_DIR}"
        rm -rf "${STATE_DIR}"
    else
        log "Keeping ${STATE_DIR} (use --purge-data to remove)"
    fi
}

main() {
    parse_args "$@"
    require_root

    remove_unit
    remove_user_group
    purge_data

    log "Uninstall complete."
}

main "$@"
