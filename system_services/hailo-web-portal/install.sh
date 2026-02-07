#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/hailo-web-portal"
SERVICE_FILE="hailo-web-portal.service"
SUDOERS_FILE="/etc/sudoers.d/hailo-web-portal-systemctl"

if ! id hailo >/dev/null 2>&1; then
    sudo useradd -r -s /usr/sbin/nologin -d /opt/hailo hailo
fi

sudo mkdir -p "${INSTALL_DIR}"
sudo chown -R hailo:hailo "${INSTALL_DIR}"

sudo cp -a "${SCRIPT_DIR}/". "${INSTALL_DIR}/"

sudo chown -R hailo:hailo "${INSTALL_DIR}"

if [ -d "${INSTALL_DIR}/venv" ]; then
    sudo rm -rf "${INSTALL_DIR}/venv"
fi

sudo -u hailo python3 -m venv "${INSTALL_DIR}/venv"
sudo -u hailo "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
sudo -u hailo "${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

cat <<EOF | sudo tee "${SUDOERS_FILE}" >/dev/null
hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hailo-*
hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hailo-*
hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hailo-*
hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hailo-device-manager
hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hailo-device-manager
hailo ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hailo-device-manager
EOF
sudo chmod 0440 "${SUDOERS_FILE}"

sudo cp "${INSTALL_DIR}/${SERVICE_FILE}" /etc/systemd/system/${SERVICE_FILE}
sudo systemctl daemon-reload
sudo systemctl enable hailo-web-portal.service
sudo systemctl restart hailo-web-portal.service

echo "hailo-web-portal installed and started."
