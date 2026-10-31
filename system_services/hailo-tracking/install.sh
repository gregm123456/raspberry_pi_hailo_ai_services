#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR=/opt/hailo-tracking
STATE_DIR=/var/lib/hailo-tracking
MODEL_DIR="${STATE_DIR}/models"
SERVICE_USER=hailo-tracking
SERVICE_GROUP=hailo-tracking
STARK_HEF_URL=https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.5.0/hailo10h/stark_lightning_repvgg_a0.hef
BYTETRACK_HEF_URL=https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.5.0/hailo10h/bytetrack_tiny_mot17.hef

if [[ ${EUID} -ne 0 ]]; then
    echo "Run as root: sudo ${BASH_SOURCE[0]}" >&2
    exit 1
fi

for command in python3 curl install systemctl; do
    command -v "${command}" >/dev/null || {
        echo "Missing required command: ${command}" >&2
        exit 1
    }
done

for group in hailo-device-mgr video; do
    if ! getent group "${group}" >/dev/null; then
        echo "Required group '${group}' is missing." >&2
        exit 1
    fi
done

getent group "${SERVICE_GROUP}" >/dev/null || groupadd --system "${SERVICE_GROUP}"
id "${SERVICE_USER}" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d "${STATE_DIR}" -g "${SERVICE_GROUP}" "${SERVICE_USER}"
usermod -aG hailo-device-mgr,video "${SERVICE_USER}"

# Keep the HEFs readable by the shared Device Manager without making them world-readable.
install -d -o root -g root -m 755 "${SERVICE_DIR}"
install -d -o root -g hailo-device-mgr -m 750 "${STATE_DIR}" "${MODEL_DIR}"

# Isolate service dependencies from system Python and other service environments.
python3 -m venv "${SERVICE_DIR}/venv"
"${SERVICE_DIR}/venv/bin/pip" install --disable-pip-version-check -r "${SCRIPT_DIR}/requirements.txt"
install -m 755 "${SCRIPT_DIR}/tracking_pipeline.py" "${SERVICE_DIR}/tracking_pipeline.py"
install -m 755 "${SCRIPT_DIR}/hailo_tracking_service.py" "${SERVICE_DIR}/hailo_tracking_service.py"

download_model() {
    local url="$1"
    local destination="$2"
    if [[ ! -s "${destination}" ]]; then
        local temporary="${destination}.download"
        # Download to a temporary path so a partial file is never treated as a valid HEF.
        if ! curl --fail --location --show-error --retry 3 "${url}" --output "${temporary}"; then
            rm -f "${temporary}"
            echo "Failed to download model: ${url}" >&2
            exit 1
        fi
        install -o root -g hailo-device-mgr -m 640 "${temporary}" "${destination}"
        rm -f "${temporary}"
    fi
    chown root:hailo-device-mgr "${destination}"
    chmod 640 "${destination}"
}

download_model "${STARK_HEF_URL}" "${MODEL_DIR}/stark_lightning_repvgg_a0.hef"
download_model "${BYTETRACK_HEF_URL}" "${MODEL_DIR}/bytetrack_tiny_mot17.hef"

chown root:hailo-device-mgr "${STATE_DIR}" "${MODEL_DIR}"
chmod 750 "${STATE_DIR}" "${MODEL_DIR}"
install -m 644 "${SCRIPT_DIR}/hailo-tracking.service" /etc/systemd/system/hailo-tracking.service
systemctl daemon-reload
systemctl enable --now hailo-tracking.service
systemctl --no-pager --full status hailo-tracking.service
