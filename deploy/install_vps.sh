#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-supertrader}"
APP_DIR="${APP_DIR:-/opt/super_trader_quant}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Execute como root (ou via sudo)." >&2
  exit 1
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "${APP_USER}"
fi

mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs" "${APP_DIR}/data/backups"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 755 "${APP_DIR}" "${APP_DIR}/data" "${APP_DIR}/logs" "${APP_DIR}/data/backups"
cd "${APP_DIR}"

if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
  sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
fi
chmod 755 "${APP_DIR}/.venv"

sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.backup_db --label pre-install --allow-missing

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.vps.example" "${APP_DIR}/.env"
  echo "Arquivo .env criado a partir de .env.vps.example; preencha os segredos antes de produção."
fi
chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

cp "${APP_DIR}/deploy/systemd/super-trader-quant-api.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/super-trader-quant-scheduler.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/super-trader-quant-watchdog.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/super-trader-quant-watchdog.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable super-trader-quant-api.service
systemctl enable super-trader-quant-scheduler.service
systemctl enable super-trader-quant-watchdog.timer

sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.seed_demo

echo "Instalação preparada."
echo "Próximos passos:"
echo "1. Preencha ${APP_DIR}/.env"
echo "2. Rode: systemctl restart super-trader-quant-api.service super-trader-quant-scheduler.service"
echo "3. Rode: systemctl start super-trader-quant-watchdog.timer"
echo "4. Rode: ${APP_DIR}/deploy/verify_vps.sh"
