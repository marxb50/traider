from __future__ import annotations

import argparse
import os
import socket
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import ROOT_DIR, settings
from super_trader_quant.backend.app.services.resource_guard_service import collect_resource_metrics
from scripts.receipt_utils import write_json_receipt


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
PLACEHOLDER_TOKENS = {"", "dummy", "dummy-token", "dummy-token-for-readiness", "changeme", "change-me"}


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw = database_url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _is_under(path: Path | None, parent: Path) -> bool:
    if path is None:
        return False
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _env_file_mode_ok(path: Path) -> bool:
    if os.name == "nt" or not path.exists():
        return True
    mode = stat.S_IMODE(path.stat().st_mode)
    return mode & 0o077 == 0


def _read_env_map(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _check(name: str, passed: bool, evidence: Any, severity: str = "error", fix: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "severity": severity,
        "evidence": evidence,
        "fix": fix,
    }


def _looks_placeholder_token(token: str) -> bool:
    token_normalized = token.strip().lower()
    return token_normalized in PLACEHOLDER_TOKENS or token_normalized.startswith("dummy")


def build_preflight_report(
    *,
    strict: bool = False,
    app_dir: str | Path = "/opt/super_trader_quant",
    env_file: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    app_root = Path(app_dir).resolve()
    data_root = app_root / "data"
    logs_root = app_root / "logs"
    env_path = Path(env_file).resolve() if env_file else app_root / ".env"
    env_values = _read_env_map(env_path)
    database_path = _sqlite_path(settings.database_url)
    log_dir = _resolve(settings.log_dir)
    backup_dir = _resolve(settings.backup_dir)
    scheduler_lock = _resolve(settings.scheduler_lock_path)
    token = settings.telegram_bot_token.strip()
    br_token = settings.telegram_br_bot_token.strip()
    ops_token = settings.ops_admin_token.strip()
    chat_ids = settings.telegram_chat_id_list
    br_chat_ids = settings.telegram_br_chat_id_list

    paper_broker = env_values.get("PAPER_BROKER", os.environ.get("PAPER_BROKER", "internal")).lower()
    allow_external_paper = env_values.get("ALLOW_EXTERNAL_PAPER", os.environ.get("ALLOW_EXTERNAL_PAPER", "false")).lower()
    resources = collect_resource_metrics()

    checks = [
        _check(
            "env_file_exists",
            env_path.exists() or not strict,
            str(env_path),
            fix="Crie/preencha o .env do VPS antes de iniciar produção.",
        ),
        _check(
            "env_file_permissions_private",
            _env_file_mode_ok(env_path),
            str(env_path),
            fix="Use chmod 600 /opt/super_trader_quant/.env.",
        ),
        _check(
            "app_env_production_when_strict",
            (not strict) or settings.app_env == "production",
            settings.app_env,
            fix="Defina APP_ENV=production no VPS.",
        ),
        _check(
            "api_host_loopback",
            settings.api_host in LOOPBACK_HOSTS,
            settings.api_host,
            fix="Defina API_HOST=127.0.0.1 para não expor a API diretamente.",
        ),
        _check(
            "api_port_dedicated",
            settings.api_port == 8010,
            settings.api_port,
            fix="Use API_PORT=8010 ou revise conscientemente todos os serviços que dependem da porta.",
        ),
        _check(
            "database_sqlite_under_app_data",
            database_path is not None and ((not strict) or _is_under(database_path, data_root)),
            str(database_path),
            fix="Use DATABASE_URL=sqlite:////opt/super_trader_quant/data/super_trader_quant.db.",
        ),
        _check(
            "log_dir_under_app_logs",
            (not strict) or _is_under(log_dir, logs_root),
            str(log_dir),
            fix="Use LOG_DIR=/opt/super_trader_quant/logs.",
        ),
        _check(
            "backup_dir_under_app_data",
            (not strict) or _is_under(backup_dir, data_root),
            str(backup_dir),
            fix="Use BACKUP_DIR=/opt/super_trader_quant/data/backups.",
        ),
        _check(
            "scheduler_lock_under_app_data",
            (not strict) or _is_under(scheduler_lock, data_root),
            str(scheduler_lock),
            fix="Use SCHEDULER_LOCK_PATH=/opt/super_trader_quant/data/scheduler.lock.",
        ),
        _check(
            "provider_not_simulated_when_strict",
            (not strict) or settings.default_provider != "simulated",
            settings.default_provider,
            fix="Use DEFAULT_PROVIDER=yfinance ou outro provider real no VPS.",
        ),
        _check(
            "telegram_token_real_when_strict",
            (not strict) or (bool(token) and not _looks_placeholder_token(token)),
            {"present": bool(token), "looks_placeholder": _looks_placeholder_token(token)},
            fix="Configure TELEGRAM_BOT_TOKEN real no .env do VPS.",
        ),
        _check(
            "ops_admin_token_real_when_strict",
            (not strict) or (bool(ops_token) and not _looks_placeholder_token(ops_token)),
            {"present": bool(ops_token), "looks_placeholder": _looks_placeholder_token(ops_token)},
            fix="Configure OPS_ADMIN_TOKEN real no .env do VPS para proteger endpoints /ops mutáveis.",
        ),
        _check(
            "telegram_chat_ids_present",
            bool(chat_ids),
            chat_ids,
            fix="Configure TELEGRAM_CHAT_IDS no .env.",
        ),
        _check(
            "telegram_br_route_consistent",
            (not br_token and not br_chat_ids)
            or (
                bool(br_token)
                and not _looks_placeholder_token(br_token)
                and bool(br_chat_ids)
            ),
            {
                "token_present": bool(br_token),
                "token_placeholder": _looks_placeholder_token(br_token) if br_token else False,
                "chat_ids": br_chat_ids,
            },
            fix="Se usar a rota BR, configure TELEGRAM_BR_BOT_TOKEN real e TELEGRAM_BR_CHAT_IDS no .env.",
        ),
        _check(
            "intervals_positive",
            min(
                settings.scan_interval_minutes,
                settings.outcome_check_interval_minutes,
                settings.notification_dispatch_interval_minutes,
                settings.watchdog_interval_minutes,
                settings.maintenance_interval_minutes,
            )
            > 0,
            {
                "scan": settings.scan_interval_minutes,
                "outcome": settings.outcome_check_interval_minutes,
                "notification": settings.notification_dispatch_interval_minutes,
                "watchdog": settings.watchdog_interval_minutes,
                "maintenance": settings.maintenance_interval_minutes,
            },
            fix="Todos os intervalos precisam ser maiores que zero.",
        ),
        _check(
            "retention_windows_positive",
            settings.sent_notification_retention_days > 0
            and settings.failed_notification_retention_days > 0
            and settings.backup_retention_days > 0
            and settings.backup_retention_max_files > 0,
            {
                "sent_notification_retention_days": settings.sent_notification_retention_days,
                "failed_notification_retention_days": settings.failed_notification_retention_days,
                "backup_retention_days": settings.backup_retention_days,
                "backup_retention_max_files": settings.backup_retention_max_files,
            },
            fix="Janelas de retenção precisam ser positivas.",
        ),
        _check(
            "resource_guard_ok",
            resources["resource_guard_ok"],
            resources,
            fix="Libere espaço em data/logs/backups ou aumente limites conscientemente no .env.",
        ),
        _check(
            "external_broker_disabled",
            paper_broker in {"", "internal", "simulated"} and allow_external_paper not in {"1", "true", "yes", "on"},
            {"PAPER_BROKER": paper_broker, "ALLOW_EXTERNAL_PAPER": allow_external_paper},
            fix="Mantenha PAPER_BROKER=internal/simulated e ALLOW_EXTERNAL_PAPER=false no MVP.",
        ),
    ]
    failures = [check for check in checks if not check["passed"] and (strict or check["severity"] == "error")]
    return {
        "ok": not failures,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "strict": strict,
        "app_dir": str(app_root),
        "env_file": str(env_path),
        "telegram_br_chat_ids": br_chat_ids,
        "checks": checks,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight seguro de produção para o SUPER_TRADER_QUANT.")
    parser.add_argument("--strict", action="store_true", help="Exige configuração real de produção.")
    parser.add_argument("--app-dir", default="/opt/super_trader_quant")
    parser.add_argument("--env-file")
    parser.add_argument("--run-id", help="Identificador opcional da rodada de verificação.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()
    report = build_preflight_report(strict=args.strict, app_dir=args.app_dir, env_file=args.env_file, run_id=args.run_id)
    if args.output:
        output_path = Path(args.output)
        write_json_receipt(output_path, report)
    print(f"ok: {report['ok']}")
    print(f"strict: {report['strict']}")
    for check in report["checks"]:
        status = "passed" if check["passed"] else "failed"
        print(f"- {status}: {check['name']} -> {check['evidence']}")
        if not check["passed"] and check["fix"]:
            print(f"  fix: {check['fix']}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
