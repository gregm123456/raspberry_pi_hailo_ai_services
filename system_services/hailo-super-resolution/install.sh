#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="hailo-super-resolution"
SERVICE_USER="${SERVICE_NAME}"
SERVICE_GROUP="${SERVICE_NAME}"
SERVICE_DIR="/opt/${SERVICE_NAME}"
STATE_DIR="/var/lib/${SERVICE_NAME}"
MODEL_DIR="${STATE_DIR}/models"
VENV_DIR="${SERVICE_DIR}/venv"
MODEL_PATH="${MODEL_DIR}/spanf_x4.hef"
MODEL_URL="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.5.0/hailo10h/spanf_x4.hef"

if [[ ${EUID} -ne 0 ]]; then
    echo "ERROR: Run this installer with sudo." >&2
    exit 1
fi

for command in curl python3 systemctl; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: ${command}" >&2
        exit 1
    fi
done

if ! getent group hailo-device-mgr >/dev/null 2>&1; then
    echo "ERROR: hailo-device-mgr group is missing; install hailo-device-manager first." >&2
    exit 1
fi

if ! getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
    groupadd --system "${SERVICE_GROUP}"
fi
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin \
        --gid "${SERVICE_GROUP}" "${SERVICE_USER}"
fi
usermod -aG hailo-device-mgr "${SERVICE_USER}"

install -d -o root -g root -m 0755 "${SERVICE_DIR}"
install -d -o root -g hailo-device-mgr -m 0750 "${STATE_DIR}" "${MODEL_DIR}"
chown root:hailo-device-mgr "${STATE_DIR}" "${MODEL_DIR}"
chmod 0750 "${STATE_DIR}" "${MODEL_DIR}"
install -m 0644 "${SCRIPT_DIR}/super_resolution.py" "${SERVICE_DIR}/super_resolution.py"
install -m 0644 "${SCRIPT_DIR}/hailo_super_resolution_service.py" \
    "${SERVICE_DIR}/hailo_super_resolution_service.py"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${SCRIPT_DIR}/requirements.txt"

if [[ ! -s "${MODEL_PATH}" ]]; then
    temporary_model="$(mktemp "${MODEL_DIR}/.spanf_x4.XXXXXX")"
    trap 'rm -f "${temporary_model}"' EXIT
    echo "Downloading the official Hailo-10H SPANF x4 HEF..."
    curl --fail --location --retry 3 --connect-timeout 20 \
        --output "${temporary_model}" "${MODEL_URL}"
    if [[ ! -s "${temporary_model}" ]]; then
        echo "ERROR: Downloaded SPANF HEF is empty." >&2
        exit 1
    fi
    install -o root -g hailo-device-mgr -m 0640 \
        "${temporary_model}" "${MODEL_PATH}"
fi
chown "root:hailo-device-mgr" "${MODEL_PATH}"
chmod 0640 "${MODEL_PATH}"

install -m 0644 "${SCRIPT_DIR}/hailo-super-resolution.service" \
    /etc/systemd/system/hailo-super-resolution.service
systemctl daemon-reload
systemctl enable --now hailo-super-resolution.service

echo "Installed ${SERVICE_NAME}; check with: systemctl status ${SERVICE_NAME}"
