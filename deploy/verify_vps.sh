#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-supertrader}"
APP_DIR="${APP_DIR:-/opt/super_trader_quant}"
RUN_ID="${RUN_ID:-vps-$(date -u +%Y%m%dT%H%M%SZ)}"
cd "${APP_DIR}"

sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.production_preflight --strict --app-dir "${APP_DIR}" --env-file "${APP_DIR}/.env" --run-id "${RUN_ID}" --output "${APP_DIR}/logs/production_preflight_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.check_deploy_readiness --strict
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.verify_filesystem_isolation --app-dir "${APP_DIR}" --app-user "${APP_USER}" --run-id "${RUN_ID}" --output "${APP_DIR}/logs/filesystem_isolation_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.verify_systemd_runtime --run-id "${RUN_ID}" --output "${APP_DIR}/logs/systemd_runtime_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.verify_process_runtime --app-user "${APP_USER}" --app-dir "${APP_DIR}" --api-port 8010 --run-id "${RUN_ID}" --output "${APP_DIR}/logs/process_runtime_last.json"
curl --fail --silent "http://127.0.0.1:8010/health" >/dev/null
curl --fail --silent "http://127.0.0.1:8010/ops/status" >/dev/null
curl --fail --silent "http://127.0.0.1:8010/ops/watchdog?strict=true" >/dev/null
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.verify_ops_http_protection --base-url "http://127.0.0.1:8010" --run-id "${RUN_ID}" --output "${APP_DIR}/logs/ops_http_protection_last.json"
systemctl is-active --quiet super-trader-quant-api.service
systemctl is-active --quiet super-trader-quant-scheduler.service
systemctl is-active --quiet super-trader-quant-watchdog.timer
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.dispatch_notifications_now --run-id "${RUN_ID}" --max-batches 20 --require-empty --output "${APP_DIR}/logs/notification_drain_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.check_deploy_readiness --strict --runtime
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.watchdog_once --strict
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.run_maintenance
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.send_telegram_canary --run-id "${RUN_ID}"
if sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" - <<'PY'
from super_trader_quant.backend.app.services.telegram_service import BRAZIL_ROUTE, get_telegram_route_chat_ids, get_telegram_route_token
raise SystemExit(0 if get_telegram_route_token(BRAZIL_ROUTE) and get_telegram_route_chat_ids(BRAZIL_ROUTE) else 1)
PY
then
  sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.send_telegram_canary --route br --run-id "${RUN_ID}"
fi
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.build_verification_manifest --run-id "${RUN_ID}" --log-dir "${APP_DIR}/logs" --output "${APP_DIR}/logs/verification_manifest_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.goal_acceptance_report --strict --runtime --require-canary --require-preflight --require-ops-protection --require-systemd-runtime --require-filesystem-isolation --require-process-runtime --require-notification-drain --require-verification-manifest --expected-run-id "${RUN_ID}" --expected-app-dir "${APP_DIR}" --expected-app-user "${APP_USER}" --expected-env-file "${APP_DIR}/.env" --expected-api-base-url "http://127.0.0.1:8010" --expected-api-port 8010 --output "${APP_DIR}/logs/goal_acceptance_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.build_verification_bundle --run-id "${RUN_ID}" --log-dir "${APP_DIR}/logs" --output-zip "${APP_DIR}/logs/verification_bundle_last.zip" --output-receipt "${APP_DIR}/logs/verification_bundle_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.verify_verification_bundle --expected-run-id "${RUN_ID}" --log-dir "${APP_DIR}/logs" --bundle-zip "${APP_DIR}/logs/verification_bundle_last.zip" --bundle-receipt "${APP_DIR}/logs/verification_bundle_last.json" --check-live-files --output "${APP_DIR}/logs/verification_bundle_check_last.json"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m scripts.verify_verification_round --expected-run-id "${RUN_ID}" --log-dir "${APP_DIR}/logs" --output "${APP_DIR}/logs/verification_round_last.json"

echo "Verificação do VPS concluída com sucesso. RUN_ID=${RUN_ID}"
