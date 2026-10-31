#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVICE_DIR=/opt/hailo-audio
STATE_DIR=/var/lib/hailo-audio
MODEL_DIR="${STATE_DIR}/resources/models/hailo10h"
SERVICE_USER=hailo-audio
SERVICE_GROUP=hailo-audio
HEF_URL=https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.5.0/hailo10h/yamnet.hef
CLASS_MAP="${REPO_ROOT}/hailo_model_zoo/hailo_model_zoo/core/postprocessing/yamnet_class_map.json"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run as root: sudo ${BASH_SOURCE[0]}" >&2
    exit 1
fi
for command in python3 curl install; do
    command -v "${command}" >/dev/null || { echo "Missing required command: ${command}" >&2; exit 1; }
done
if [[ ! -f "${CLASS_MAP}" ]]; then
    echo "YamNet class map not found; initialize the hailo_model_zoo submodule." >&2
    exit 1
fi
if ! getent group hailo-device-mgr >/dev/null; then
    echo "hailo-device-mgr group is missing; install hailo-device-manager first." >&2
    exit 1
fi

getent group "${SERVICE_GROUP}" >/dev/null || groupadd --system "${SERVICE_GROUP}"
id "${SERVICE_USER}" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d "${STATE_DIR}" -g "${SERVICE_GROUP}" "${SERVICE_USER}"
usermod -aG hailo-device-mgr "${SERVICE_USER}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" "${STATE_DIR}/resources" "${MODEL_DIR}"
install -d -o root -g root "${SERVICE_DIR}"
python3 -m venv "${SERVICE_DIR}/venv"
"${SERVICE_DIR}/venv/bin/pip" install --disable-pip-version-check -r "${SCRIPT_DIR}/requirements.txt"
install -m 755 "${SCRIPT_DIR}/hailo_audio_server.py" "${SERVICE_DIR}/hailo_audio_server.py"
install -m 644 "${CLASS_MAP}" "${STATE_DIR}/resources/yamnet_class_map.json"
if [[ ! -s "${MODEL_DIR}/yamnet.hef" ]]; then
    temp_file="${MODEL_DIR}/yamnet.hef.download"
    trap 'rm -f "${temp_file}"' EXIT
    curl --fail --location --show-error --retry 3 "${HEF_URL}" -o "${temp_file}"
    install -o root -g root -m 644 "${temp_file}" "${MODEL_DIR}/yamnet.hef"
    rm -f "${temp_file}"
    trap - EXIT
fi
install -m 644 "${SCRIPT_DIR}/hailo-audio.service" /etc/systemd/system/hailo-audio.service
systemctl daemon-reload
systemctl enable --now hailo-audio.service
systemctl --no-pager --full status hailo-audio.service
