from __future__ import annotations

from pathlib import Path

from super_trader_quant.backend.app.config import ROOT_DIR


REQUIRED_SERVICE_SNIPPETS = [
    "User=supertrader",
    "WorkingDirectory=/opt/super_trader_quant",
    "EnvironmentFile=/opt/super_trader_quant/.env",
    "UMask=0077",
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "ProtectSystem=strict",
    "ProtectHome=true",
    "ReadWritePaths=/opt/super_trader_quant/data /opt/super_trader_quant/logs",
    "ProtectKernelTunables=true",
    "ProtectKernelModules=true",
    "ProtectControlGroups=true",
    "RestrictSUIDSGID=true",
    "LockPersonality=true",
]


def _contains_all(path: Path, snippets: list[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [snippet for snippet in snippets if snippet not in text]


def validate_deploy_artifacts(root_dir: Path = ROOT_DIR) -> dict[str, object]:
    paths = {
        "api_service": root_dir / "deploy/systemd/super-trader-quant-api.service",
        "scheduler_service": root_dir / "deploy/systemd/super-trader-quant-scheduler.service",
        "watchdog_service": root_dir / "deploy/systemd/super-trader-quant-watchdog.service",
        "watchdog_timer": root_dir / "deploy/systemd/super-trader-quant-watchdog.timer",
        "docker_compose": root_dir / "deploy/docker-compose.yml",
        "install_vps": root_dir / "deploy/install_vps.sh",
        "verify_vps": root_dir / "deploy/verify_vps.sh",
        "env_vps": root_dir / ".env.vps.example",
    }
    issues: list[str] = []
    missing_paths = [name for name, path in paths.items() if not path.exists()]
    for name in missing_paths:
        issues.append(f"arquivo ausente: {name} -> {paths[name]}")
    if missing_paths:
        return {"ok": False, "issues": issues, "paths": {key: str(value) for key, value in paths.items()}}

    service_expectations = {
        "api_service": ["ExecStart=/opt/super_trader_quant/.venv/bin/python -m scripts.run_api"],
        "scheduler_service": ["ExecStart=/opt/super_trader_quant/.venv/bin/python -m scripts.run_scheduler"],
        "watchdog_service": ["Type=oneshot", "ExecStart=/opt/super_trader_quant/.venv/bin/python -m scripts.watchdog_once --strict"],
    }
    for name, extra_snippets in service_expectations.items():
        missing = _contains_all(paths[name], [*REQUIRED_SERVICE_SNIPPETS, *extra_snippets])
        for snippet in missing:
            issues.append(f"{name} sem trecho obrigatório: {snippet}")

    timer_missing = _contains_all(
        paths["watchdog_timer"],
        [
            "OnBootSec=2min",
            "OnUnitActiveSec=5min",
            "Unit=super-trader-quant-watchdog.service",
            "WantedBy=timers.target",
        ],
    )
    for snippet in timer_missing:
        issues.append(f"watchdog_timer sem trecho obrigatório: {snippet}")

    docker_text = paths["docker_compose"].read_text(encoding="utf-8")
    docker_snippets = [
        "api:",
        "scheduler:",
        "watchdog:",
        "127.0.0.1:8010:8010",
        "python -m scripts.run_api",
        "python -m scripts.run_scheduler",
        "python -m scripts.run_watchdog_loop",
        "../data:/app/data",
        "../logs:/app/logs",
    ]
    for snippet in docker_snippets:
        if snippet not in docker_text:
            issues.append(f"docker_compose sem trecho obrigatório: {snippet}")

    install_text = paths["install_vps"].read_text(encoding="utf-8")
    install_snippets = [
        "useradd --system --create-home --shell /bin/bash",
        "mkdir -p \"${APP_DIR}/data\" \"${APP_DIR}/logs\" \"${APP_DIR}/data/backups\"",
        "cd \"${APP_DIR}\"",
        "scripts.backup_db --label pre-install --allow-missing",
        "chmod 755 \"${APP_DIR}\" \"${APP_DIR}/data\" \"${APP_DIR}/logs\" \"${APP_DIR}/data/backups\"",
        "chmod 755 \"${APP_DIR}/.venv\"",
        "chmod 600 \"${APP_DIR}/.env\"",
        "super-trader-quant-watchdog.service",
        "super-trader-quant-watchdog.timer",
        "systemctl enable super-trader-quant-watchdog.timer",
        "scripts.seed_demo",
    ]
    for snippet in install_snippets:
        if snippet not in install_text:
            issues.append(f"install_vps sem trecho obrigatório: {snippet}")

    verify_text = paths["verify_vps"].read_text(encoding="utf-8")
    verify_snippets = [
        "RUN_ID=",
        "cd \"${APP_DIR}\"",
        "scripts.production_preflight --strict",
        "--run-id \"${RUN_ID}\"",
        "logs/production_preflight_last.json",
        "scripts.check_deploy_readiness --strict",
        "scripts.verify_filesystem_isolation --app-dir",
        "logs/filesystem_isolation_last.json",
        "scripts.verify_systemd_runtime --run-id",
        "logs/systemd_runtime_last.json",
        "scripts.verify_process_runtime --app-user",
        "logs/process_runtime_last.json",
        "curl --fail --silent \"http://127.0.0.1:8010/health\"",
        "curl --fail --silent \"http://127.0.0.1:8010/ops/status\"",
        "curl --fail --silent \"http://127.0.0.1:8010/ops/watchdog?strict=true\"",
        "scripts.verify_ops_http_protection --base-url \"http://127.0.0.1:8010\"",
        "logs/ops_http_protection_last.json",
        "systemctl is-active --quiet super-trader-quant-api.service",
        "systemctl is-active --quiet super-trader-quant-scheduler.service",
        "systemctl is-active --quiet super-trader-quant-watchdog.timer",
        "scripts.dispatch_notifications_now --run-id \"${RUN_ID}\" --max-batches 20 --require-empty",
        "logs/notification_drain_last.json",
        "scripts.check_deploy_readiness --strict --runtime",
        "scripts.watchdog_once --strict",
        "scripts.run_maintenance",
        "scripts.send_telegram_canary",
        "scripts.build_verification_manifest --run-id \"${RUN_ID}\" --log-dir \"${APP_DIR}/logs\"",
        "logs/verification_manifest_last.json",
        "--expected-run-id \"${RUN_ID}\"",
        "--expected-app-dir \"${APP_DIR}\"",
        "--expected-app-user \"${APP_USER}\"",
        "--expected-env-file \"${APP_DIR}/.env\"",
        "--expected-api-base-url \"http://127.0.0.1:8010\"",
        "--expected-api-port 8010",
        "--require-verification-manifest",
        "scripts.goal_acceptance_report --strict --runtime --require-canary --require-preflight --require-ops-protection --require-systemd-runtime --require-filesystem-isolation --require-process-runtime --require-notification-drain",
        "scripts.build_verification_bundle --run-id \"${RUN_ID}\" --log-dir \"${APP_DIR}/logs\"",
        "logs/verification_bundle_last.zip",
        "logs/verification_bundle_last.json",
        "scripts.verify_verification_bundle --expected-run-id \"${RUN_ID}\" --log-dir \"${APP_DIR}/logs\"",
        "logs/verification_bundle_check_last.json",
        "scripts.verify_verification_round --expected-run-id \"${RUN_ID}\" --log-dir \"${APP_DIR}/logs\"",
        "logs/verification_round_last.json",
    ]
    for snippet in verify_snippets:
        if snippet not in verify_text:
            issues.append(f"verify_vps sem trecho obrigatório: {snippet}")

    env_text = paths["env_vps"].read_text(encoding="utf-8")
    env_snippets = [
        "APP_ENV=production",
        "DATABASE_URL=sqlite:////opt/super_trader_quant/data/super_trader_quant.db",
        "DEFAULT_PROVIDER=yfinance",
        "API_HOST=127.0.0.1",
        "TELEGRAM_CHAT_IDS=",
        "OPS_ADMIN_TOKEN=",
        "SCHEDULER_LOCK_PATH=/opt/super_trader_quant/data/scheduler.lock",
        "BACKUP_DIR=/opt/super_trader_quant/data/backups",
        "WATCHDOG_INTERVAL_MINUTES=5",
        "SCHEDULER_STARTUP_GRACE_SECONDS=120",
        "MAINTENANCE_INTERVAL_MINUTES=1440",
        "SENT_NOTIFICATION_RETENTION_DAYS=30",
        "FAILED_NOTIFICATION_RETENTION_DAYS=90",
        "MIN_FREE_DISK_MB=512",
        "MAX_DATABASE_SIZE_MB=2048",
        "BACKUP_RETENTION_DAYS=30",
        "BACKUP_RETENTION_MAX_FILES=60",
    ]
    for snippet in env_snippets:
        if snippet not in env_text:
            issues.append(f"env_vps sem trecho obrigatório: {snippet}")

    return {
        "ok": not issues,
        "issues": issues,
        "paths": {key: str(value) for key, value in paths.items()},
    }


def main() -> None:
    report = validate_deploy_artifacts()
    print(f"ok: {report['ok']}")
    for issue in report["issues"]:
        print(f"- {issue}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
