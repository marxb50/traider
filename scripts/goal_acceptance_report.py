from __future__ import annotations

import argparse
import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.demo_assets import EXPECTED_ASSET_COUNT, EXPECTED_ASSETS_BY_MARKET
from super_trader_quant.backend.app.services.watchdog_service import collect_watchdog_report
from scripts.check_deploy_readiness import build_report as build_readiness_report
from scripts.receipt_utils import hash_file_sha256, write_json_receipt
from scripts.validate_deploy_artifacts import validate_deploy_artifacts


CANARY_RECEIPT_FILE = "telegram_canary_last.json"
PREFLIGHT_RECEIPT_FILE = "production_preflight_last.json"
OPS_HTTP_PROTECTION_RECEIPT_FILE = "ops_http_protection_last.json"
SYSTEMD_RUNTIME_RECEIPT_FILE = "systemd_runtime_last.json"
FILESYSTEM_ISOLATION_RECEIPT_FILE = "filesystem_isolation_last.json"
PROCESS_RUNTIME_RECEIPT_FILE = "process_runtime_last.json"
NOTIFICATION_DRAIN_RECEIPT_FILE = "notification_drain_last.json"
VERIFICATION_MANIFEST_RECEIPT_FILE = "verification_manifest_last.json"
RECEIPT_MAX_AGE_MINUTES = 120
EXPECTED_VPS_APP_DIR = "/opt/super_trader_quant"
EXPECTED_VPS_APP_USER = "supertrader"
EXPECTED_VPS_API_BASE_URL = "http://127.0.0.1:8010"
EXPECTED_VPS_API_PORT = 8010


@dataclass
class AcceptanceItem:
    requirement: str
    status: str
    evidence: Any
    blocker: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def _item(requirement: str, condition: bool, evidence: Any, blocker: str | None = None) -> AcceptanceItem:
    return AcceptanceItem(
        requirement=requirement,
        status="passed" if condition else "blocked",
        evidence=evidence,
        blocker=None if condition else blocker,
    )


def _load_json_receipt(filename: str) -> dict[str, Any] | None:
    path = settings.resolved_log_dir / filename
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "_receipt_path": str(path),
            "_receipt_mtime": mtime,
            "_invalid_json_error": str(exc),
        }
    receipt["_receipt_path"] = str(path)
    receipt["_receipt_mtime"] = mtime
    return receipt


def _parse_receipt_timestamp(receipt: dict[str, Any] | None) -> tuple[datetime | None, str | None]:
    if not receipt:
        return None, None
    generated_at = receipt.get("generated_at")
    if isinstance(generated_at, str):
        try:
            parsed = datetime.fromisoformat(generated_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc), "generated_at"
        except ValueError:
            pass
    base_key = receipt.get("base_key")
    if isinstance(base_key, str) and base_key.startswith("telegram_canary:"):
        raw_timestamp = base_key.removeprefix("telegram_canary:")
        try:
            parsed = datetime.strptime(raw_timestamp, "%Y%m%d-%H%M%S-%f").replace(tzinfo=timezone.utc)
            return parsed, "base_key"
        except ValueError:
            pass
    fallback_mtime = receipt.get("_receipt_mtime")
    if isinstance(fallback_mtime, str):
        try:
            parsed = datetime.fromisoformat(fallback_mtime)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc), "file_mtime"
        except ValueError:
            pass
    return None, None


def _receipt_freshness(receipt: dict[str, Any] | None, *, max_age_minutes: int = RECEIPT_MAX_AGE_MINUTES) -> dict[str, Any]:
    if not receipt:
        return {
            "ok": False,
            "timestamp": None,
            "timestamp_source": None,
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "reason": "missing_receipt",
        }
    if receipt.get("_invalid_json_error"):
        return {
            "ok": False,
            "timestamp": None,
            "timestamp_source": None,
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "reason": "invalid_json",
        }
    timestamp, source = _parse_receipt_timestamp(receipt)
    if timestamp is None:
        return {
            "ok": False,
            "timestamp": None,
            "timestamp_source": None,
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "reason": "missing_timestamp",
        }
    age_minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60
    return {
        "ok": age_minutes <= max_age_minutes,
        "timestamp": timestamp.isoformat(),
        "timestamp_source": source,
        "age_minutes": age_minutes,
        "max_age_minutes": max_age_minutes,
        "reason": "fresh" if age_minutes <= max_age_minutes else "stale_receipt",
    }


def _receipt_run_id(receipt: dict[str, Any] | None, *, expected_run_id: str | None) -> dict[str, Any]:
    actual_run_id = receipt.get("run_id") if receipt else None
    if not expected_run_id:
        return {
            "ok": True,
            "expected_run_id": None,
            "actual_run_id": actual_run_id,
            "reason": "not_required",
        }
    if not receipt:
        return {
            "ok": False,
            "expected_run_id": expected_run_id,
            "actual_run_id": actual_run_id,
            "reason": "missing_receipt",
        }
    if receipt.get("_invalid_json_error"):
        return {
            "ok": False,
            "expected_run_id": expected_run_id,
            "actual_run_id": actual_run_id,
            "reason": "invalid_json",
        }
    if not actual_run_id:
        return {
            "ok": False,
            "expected_run_id": expected_run_id,
            "actual_run_id": actual_run_id,
            "reason": "missing_run_id",
        }
    return {
        "ok": actual_run_id == expected_run_id,
        "expected_run_id": expected_run_id,
        "actual_run_id": actual_run_id,
        "reason": "match" if actual_run_id == expected_run_id else "mismatch",
    }


def _receipt_identity(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not receipt:
        return {
            "hostname": None,
            "app_env": None,
            "ok": False,
            "reason": "missing_receipt",
        }
    if receipt.get("_invalid_json_error"):
        return {
            "hostname": None,
            "app_env": None,
            "ok": False,
            "reason": "invalid_json",
        }
    hostname = receipt.get("hostname")
    app_env = receipt.get("app_env")
    return {
        "hostname": hostname,
        "app_env": app_env,
        "ok": bool(hostname) and bool(app_env),
        "reason": "ok" if hostname and app_env else "missing_identity_fields",
    }


def _receipts_host_coherence(receipts: list[dict[str, Any] | None], *, strict: bool) -> dict[str, Any]:
    identities = [_receipt_identity(receipt) for receipt in receipts if receipt is not None]
    if not identities:
        return {
            "ok": True,
            "hostnames": [],
            "app_envs": [],
            "reason": "no_receipts_required",
        }
    if any(not identity["ok"] for identity in identities):
        return {
            "ok": False,
            "hostnames": [identity["hostname"] for identity in identities],
            "app_envs": [identity["app_env"] for identity in identities],
            "reason": "missing_identity_fields",
        }
    hostnames = sorted({str(identity["hostname"]) for identity in identities})
    app_envs = sorted({str(identity["app_env"]) for identity in identities})
    same_host = len(hostnames) == 1
    production_env = (not strict) or app_envs == ["production"]
    return {
        "ok": same_host and production_env,
        "hostnames": hostnames,
        "app_envs": app_envs,
        "reason": "ok" if same_host and production_env else "host_or_env_mismatch",
    }


def _receipt_parameter_coherence(
    *,
    preflight_receipt: dict[str, Any] | None,
    ops_http_receipt: dict[str, Any] | None,
    filesystem_isolation_receipt: dict[str, Any] | None,
    process_runtime_receipt: dict[str, Any] | None,
    require_preflight: bool,
    require_ops_protection: bool,
    require_filesystem_isolation: bool,
    require_process_runtime: bool,
    expected_app_dir: str,
    expected_app_user: str,
    expected_env_file: str,
    expected_api_base_url: str,
    expected_api_port: int,
    strict: bool,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    def _skip(reason: str) -> dict[str, Any]:
        return {"ok": True, "reason": reason}

    def _missing_or_invalid(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
        if receipt is None:
            return _skip("missing_receipt_already_handled")
        if receipt.get("_invalid_json_error"):
            return _skip("invalid_receipt_already_handled")
        return None

    if require_preflight:
        handled = _missing_or_invalid(preflight_receipt)
        if handled is not None:
            checks["preflight"] = handled
        else:
            actual = {
                "strict": preflight_receipt.get("strict"),
                "app_dir": preflight_receipt.get("app_dir"),
                "env_file": preflight_receipt.get("env_file"),
                "app_env": preflight_receipt.get("app_env"),
            }
            expected = {
                "strict": strict,
                "app_dir": expected_app_dir,
                "env_file": expected_env_file,
                "app_env": "production" if strict else None,
            }
            ok = (
                actual["strict"] == strict
                and actual["app_dir"] == expected_app_dir
                and actual["env_file"] == expected_env_file
                and ((not strict) or actual["app_env"] == "production")
            )
            checks["preflight"] = {"ok": ok, "actual": actual, "expected": expected}

    if require_ops_protection:
        handled = _missing_or_invalid(ops_http_receipt)
        if handled is not None:
            checks["ops_http"] = handled
        else:
            actual = {"base_url": ops_http_receipt.get("base_url")}
            expected = {"base_url": expected_api_base_url}
            checks["ops_http"] = {"ok": actual["base_url"] == expected_api_base_url, "actual": actual, "expected": expected}

    if require_filesystem_isolation:
        handled = _missing_or_invalid(filesystem_isolation_receipt)
        if handled is not None:
            checks["filesystem_isolation"] = handled
        else:
            actual = {
                "app_dir": filesystem_isolation_receipt.get("app_dir"),
                "app_user": filesystem_isolation_receipt.get("app_user"),
            }
            expected = {"app_dir": expected_app_dir, "app_user": expected_app_user}
            checks["filesystem_isolation"] = {
                "ok": actual["app_dir"] == expected_app_dir and actual["app_user"] == expected_app_user,
                "actual": actual,
                "expected": expected,
            }

    if require_process_runtime:
        handled = _missing_or_invalid(process_runtime_receipt)
        if handled is not None:
            checks["process_runtime"] = handled
        else:
            actual = {
                "app_dir": process_runtime_receipt.get("app_dir"),
                "app_user": process_runtime_receipt.get("app_user"),
                "api_port": process_runtime_receipt.get("api_port"),
            }
            expected = {
                "app_dir": expected_app_dir,
                "app_user": expected_app_user,
                "api_port": expected_api_port,
            }
            checks["process_runtime"] = {
                "ok": (
                    actual["app_dir"] == expected_app_dir
                    and actual["app_user"] == expected_app_user
                    and actual["api_port"] == expected_api_port
                ),
                "actual": actual,
                "expected": expected,
            }

    mismatches = {name: detail for name, detail in checks.items() if not detail.get("ok", False)}
    return {
        "ok": not mismatches,
        "checks": checks,
        "reason": "ok" if not mismatches else "parameter_mismatch",
        "mismatches": mismatches,
    }


def _verification_manifest_coherence(
    manifest_receipt: dict[str, Any] | None,
    *,
    required_receipt_filenames: list[str],
    expected_run_id: str | None,
) -> dict[str, Any]:
    if manifest_receipt is None:
        return {"ok": False, "reason": "missing_manifest"}
    if manifest_receipt.get("_invalid_json_error"):
        return {"ok": False, "reason": "invalid_manifest_json", "error": manifest_receipt.get("_invalid_json_error")}
    if not manifest_receipt.get("ok"):
        return {"ok": False, "reason": "manifest_not_ok", "issues": manifest_receipt.get("issues")}
    if expected_run_id and manifest_receipt.get("run_id") != expected_run_id:
        return {
            "ok": False,
            "reason": "manifest_run_id_mismatch",
            "expected_run_id": expected_run_id,
            "actual_run_id": manifest_receipt.get("run_id"),
        }

    receipts = manifest_receipt.get("receipts")
    if not isinstance(receipts, dict):
        return {"ok": False, "reason": "manifest_missing_receipts"}

    mismatches: dict[str, Any] = {}
    for filename in required_receipt_filenames:
        entry = receipts.get(filename)
        if not isinstance(entry, dict):
            mismatches[filename] = {"reason": "missing_manifest_entry"}
            continue
        path = settings.resolved_log_dir / filename
        if not path.exists():
            mismatches[filename] = {"reason": "missing_live_receipt"}
            continue
        live_hash = hash_file_sha256(path)
        manifest_hash = entry.get("sha256")
        if live_hash != manifest_hash:
            mismatches[filename] = {
                "reason": "hash_mismatch",
                "live_hash": live_hash,
                "manifest_hash": manifest_hash,
            }
    return {
        "ok": not mismatches,
        "reason": "ok" if not mismatches else "manifest_hash_mismatch",
        "mismatches": mismatches,
    }


def build_acceptance_report(
    *,
    strict: bool = False,
    runtime: bool = False,
    require_canary: bool = False,
    require_preflight: bool = False,
    require_ops_protection: bool = False,
    require_systemd_runtime: bool = False,
    require_filesystem_isolation: bool = False,
    require_process_runtime: bool = False,
    require_notification_drain: bool = False,
    require_verification_manifest: bool = False,
    expected_run_id: str | None = None,
    expected_app_dir: str = EXPECTED_VPS_APP_DIR,
    expected_app_user: str = EXPECTED_VPS_APP_USER,
    expected_env_file: str | None = None,
    expected_api_base_url: str = EXPECTED_VPS_API_BASE_URL,
    expected_api_port: int = EXPECTED_VPS_API_PORT,
) -> dict[str, Any]:
    init_db()
    readiness = build_readiness_report(strict=strict, runtime=runtime)
    deploy = validate_deploy_artifacts()
    with Session(engine) as session:
        watchdog = collect_watchdog_report(session, strict=strict)
    canary_receipt = _load_json_receipt(CANARY_RECEIPT_FILE)
    preflight_receipt = _load_json_receipt(PREFLIGHT_RECEIPT_FILE)
    ops_http_receipt = _load_json_receipt(OPS_HTTP_PROTECTION_RECEIPT_FILE)
    systemd_runtime_receipt = _load_json_receipt(SYSTEMD_RUNTIME_RECEIPT_FILE)
    filesystem_isolation_receipt = _load_json_receipt(FILESYSTEM_ISOLATION_RECEIPT_FILE)
    process_runtime_receipt = _load_json_receipt(PROCESS_RUNTIME_RECEIPT_FILE)
    notification_drain_receipt = _load_json_receipt(NOTIFICATION_DRAIN_RECEIPT_FILE)
    verification_manifest_receipt = _load_json_receipt(VERIFICATION_MANIFEST_RECEIPT_FILE)
    canary_freshness = _receipt_freshness(canary_receipt)
    preflight_freshness = _receipt_freshness(preflight_receipt)
    ops_http_freshness = _receipt_freshness(ops_http_receipt)
    systemd_runtime_freshness = _receipt_freshness(systemd_runtime_receipt)
    filesystem_isolation_freshness = _receipt_freshness(filesystem_isolation_receipt)
    process_runtime_freshness = _receipt_freshness(process_runtime_receipt)
    notification_drain_freshness = _receipt_freshness(notification_drain_receipt)
    verification_manifest_freshness = _receipt_freshness(verification_manifest_receipt)
    canary_run_id = _receipt_run_id(canary_receipt, expected_run_id=expected_run_id)
    preflight_run_id = _receipt_run_id(preflight_receipt, expected_run_id=expected_run_id)
    ops_http_run_id = _receipt_run_id(ops_http_receipt, expected_run_id=expected_run_id)
    systemd_runtime_run_id = _receipt_run_id(systemd_runtime_receipt, expected_run_id=expected_run_id)
    filesystem_isolation_run_id = _receipt_run_id(filesystem_isolation_receipt, expected_run_id=expected_run_id)
    process_runtime_run_id = _receipt_run_id(process_runtime_receipt, expected_run_id=expected_run_id)
    notification_drain_run_id = _receipt_run_id(notification_drain_receipt, expected_run_id=expected_run_id)
    verification_manifest_run_id = _receipt_run_id(verification_manifest_receipt, expected_run_id=expected_run_id)
    required_receipts: list[dict[str, Any] | None] = []
    if require_canary:
        required_receipts.append(canary_receipt)
    if require_preflight:
        required_receipts.append(preflight_receipt)
    if require_ops_protection:
        required_receipts.append(ops_http_receipt)
    if require_systemd_runtime:
        required_receipts.append(systemd_runtime_receipt)
    if require_filesystem_isolation:
        required_receipts.append(filesystem_isolation_receipt)
    if require_process_runtime:
        required_receipts.append(process_runtime_receipt)
    if require_notification_drain:
        required_receipts.append(notification_drain_receipt)
    receipt_host_coherence = _receipts_host_coherence(required_receipts, strict=strict)
    resolved_expected_env_file = expected_env_file or f"{expected_app_dir.rstrip('/')}/.env"
    receipt_parameter_coherence = _receipt_parameter_coherence(
        preflight_receipt=preflight_receipt,
        ops_http_receipt=ops_http_receipt,
        filesystem_isolation_receipt=filesystem_isolation_receipt,
        process_runtime_receipt=process_runtime_receipt,
        require_preflight=require_preflight,
        require_ops_protection=require_ops_protection,
        require_filesystem_isolation=require_filesystem_isolation,
        require_process_runtime=require_process_runtime,
        expected_app_dir=expected_app_dir,
        expected_app_user=expected_app_user,
        expected_env_file=resolved_expected_env_file,
        expected_api_base_url=expected_api_base_url,
        expected_api_port=expected_api_port,
        strict=strict,
    )
    canary_ok = bool(canary_receipt and canary_receipt.get("ok") and canary_freshness["ok"] and canary_run_id["ok"])
    preflight_ok = bool(preflight_receipt and preflight_receipt.get("ok") and preflight_freshness["ok"] and preflight_run_id["ok"])
    ops_http_ok = bool(ops_http_receipt and ops_http_receipt.get("ok") and ops_http_freshness["ok"] and ops_http_run_id["ok"])
    systemd_runtime_ok = bool(systemd_runtime_receipt and systemd_runtime_receipt.get("ok") and systemd_runtime_freshness["ok"] and systemd_runtime_run_id["ok"])
    filesystem_isolation_ok = bool(filesystem_isolation_receipt and filesystem_isolation_receipt.get("ok") and filesystem_isolation_freshness["ok"] and filesystem_isolation_run_id["ok"])
    process_runtime_ok = bool(process_runtime_receipt and process_runtime_receipt.get("ok") and process_runtime_freshness["ok"] and process_runtime_run_id["ok"])
    notification_drain_ok = bool(
        notification_drain_receipt
        and notification_drain_receipt.get("ok")
        and notification_drain_freshness["ok"]
        and notification_drain_run_id["ok"]
    )
    required_receipt_filenames = [
        filename
        for required, filename in [
            (require_canary, CANARY_RECEIPT_FILE),
            (require_preflight, PREFLIGHT_RECEIPT_FILE),
            (require_ops_protection, OPS_HTTP_PROTECTION_RECEIPT_FILE),
            (require_systemd_runtime, SYSTEMD_RUNTIME_RECEIPT_FILE),
            (require_filesystem_isolation, FILESYSTEM_ISOLATION_RECEIPT_FILE),
            (require_process_runtime, PROCESS_RUNTIME_RECEIPT_FILE),
            (require_notification_drain, NOTIFICATION_DRAIN_RECEIPT_FILE),
        ]
        if required
    ]
    verification_manifest_hash_coherence = _verification_manifest_coherence(
        verification_manifest_receipt,
        required_receipt_filenames=required_receipt_filenames,
        expected_run_id=expected_run_id,
    )
    verification_manifest_ok = bool(
        verification_manifest_receipt
        and verification_manifest_receipt.get("ok")
        and verification_manifest_freshness["ok"]
        and verification_manifest_run_id["ok"]
        and verification_manifest_hash_coherence["ok"]
    )

    checks = readiness["checks"]
    items = [
        _item(
            f"Universo demo esperado ({EXPECTED_ASSET_COUNT} ativos)",
            checks["active_asset_count_matches_expected"] and checks["active_asset_split_matches_expected"],
            {
                "active_asset_count": readiness["active_asset_count"],
                "active_assets_by_market": readiness["active_assets_by_market"],
                "expected_active_asset_count": readiness.get("expected_active_asset_count", EXPECTED_ASSET_COUNT),
                "expected_active_assets_by_market": readiness.get("expected_active_assets_by_market", EXPECTED_ASSETS_BY_MARKET),
            },
            f"Seed demo ainda não está com {EXPECTED_ASSET_COUNT} ativos ativos no split esperado {EXPECTED_ASSETS_BY_MARKET}.",
        ),
        _item(
            "Memória de desfecho dos sinais consistente",
            checks["memory_consistent"],
            readiness["memory_consistency"],
            "Memória histórica diverge dos sinais resolvidos; rode scripts.rebuild_memory e revalide.",
        ),
        _item(
            "Scheduler 24/7 configurado",
            checks["scheduler_jobs_ok"],
            {"scheduler_jobs": readiness["scheduler_jobs"]},
            "Jobs esperados do scheduler não estão configurados.",
        ),
        _item(
            "Runtime 24/7 saudável",
            (not runtime)
            or (
                checks["scheduler_heartbeat_present"]
                and checks["scheduler_heartbeat_not_starting"]
                and checks["scheduler_heartbeat_fresh"]
                and checks["no_stale_open_signals"]
                and checks["no_stale_pending_notifications"]
            ),
            {
                "runtime_required": runtime,
                "scheduler_heartbeat": readiness["scheduler_heartbeat"],
                "scheduler_heartbeat_age_seconds": readiness["scheduler_heartbeat_age_seconds"],
                "ops_metrics": readiness["ops_metrics"],
            },
            "Runtime não provado: scheduler sem heartbeat fresco, sinais velhos ou fila Telegram travada.",
        ),
        _item(
            "Deploy isolado do VPS validado estaticamente",
            deploy["ok"] and checks["deploy_artifacts_valid"],
            deploy,
            "Artefatos de deploy não passaram na validação de isolamento/hardening.",
        ),
        _item(
            "Watchdog operacional saudável",
            watchdog["ok"],
            watchdog,
            "Watchdog encontrou problemas operacionais; veja issues no relatório.",
        ),
        _item(
            "Telegram configurado",
            bool(settings.telegram_chat_id_list) and (not strict or bool(settings.telegram_bot_token)),
            {
                "telegram_chat_ids": settings.telegram_chat_id_list,
                "telegram_token_present": bool(settings.telegram_bot_token),
                "strict_required": strict,
            },
            "Configure TELEGRAM_BOT_TOKEN real e TELEGRAM_CHAT_IDS no .env do VPS.",
        ),
        _item(
            "Token administrativo ops configurado quando strict",
            (not strict) or bool(settings.ops_admin_token),
            {
                "ops_admin_token_present": bool(settings.ops_admin_token),
                "strict_required": strict,
            },
            "Configure OPS_ADMIN_TOKEN no .env do VPS para proteger endpoints /ops mutáveis.",
        ),
        _item(
            "Provider de produção quando strict",
            (not strict) or settings.default_provider != "simulated",
            {
                "default_provider": settings.default_provider,
                "strict_required": strict,
            },
            "Em produção, DEFAULT_PROVIDER deve ser yfinance ou outro provider real, não simulated.",
        ),
        _item(
            "Canário Telegram via outbox quando exigido",
            (not require_canary) or canary_ok,
            {"require_canary": require_canary, "latest_receipt": canary_receipt, "freshness": canary_freshness, "run_id": canary_run_id},
            "Rode python -m scripts.send_telegram_canary no VPS com token real e confirme status sent para todos os IDs; o recibo precisa ser recente e da mesma rodada.",
        ),
        _item(
            "Preflight de produção quando exigido",
            (not require_preflight) or preflight_ok,
            {"require_preflight": require_preflight, "latest_receipt": preflight_receipt, "freshness": preflight_freshness, "run_id": preflight_run_id},
            "Rode python -m scripts.production_preflight --strict no VPS e gere logs/production_preflight_last.json recente e da mesma rodada.",
        ),
        _item(
            "Proteção HTTP dos endpoints operacionais quando exigida",
            (not require_ops_protection) or ops_http_ok,
            {"require_ops_protection": require_ops_protection, "latest_receipt": ops_http_receipt, "freshness": ops_http_freshness, "run_id": ops_http_run_id},
            "Rode python -m scripts.verify_ops_http_protection no VPS e gere logs/ops_http_protection_last.json recente e da mesma rodada.",
        ),
        _item(
            "Runtime systemd isolado no VPS quando exigido",
            (not require_systemd_runtime) or systemd_runtime_ok,
            {"require_systemd_runtime": require_systemd_runtime, "latest_receipt": systemd_runtime_receipt, "freshness": systemd_runtime_freshness, "run_id": systemd_runtime_run_id},
            "Rode python -m scripts.verify_systemd_runtime no VPS e gere logs/systemd_runtime_last.json recente e da mesma rodada.",
        ),
        _item(
            "Ownership e permissões do app no VPS quando exigidos",
            (not require_filesystem_isolation) or filesystem_isolation_ok,
            {
                "require_filesystem_isolation": require_filesystem_isolation,
                "latest_receipt": filesystem_isolation_receipt,
                "freshness": filesystem_isolation_freshness,
                "run_id": filesystem_isolation_run_id,
            },
            "Rode python -m scripts.verify_filesystem_isolation no VPS e gere logs/filesystem_isolation_last.json recente e da mesma rodada.",
        ),
        _item(
            "Processos e bind de runtime do VPS quando exigidos",
            (not require_process_runtime) or process_runtime_ok,
            {
                "require_process_runtime": require_process_runtime,
                "latest_receipt": process_runtime_receipt,
                "freshness": process_runtime_freshness,
                "run_id": process_runtime_run_id,
            },
            "Rode python -m scripts.verify_process_runtime no VPS e gere logs/process_runtime_last.json recente e da mesma rodada.",
        ),
        _item(
            "Drenagem da outbox quando exigida",
            (not require_notification_drain) or notification_drain_ok,
            {
                "require_notification_drain": require_notification_drain,
                "latest_receipt": notification_drain_receipt,
                "freshness": notification_drain_freshness,
                "run_id": notification_drain_run_id,
            },
            "Rode python -m scripts.dispatch_notifications_now --require-empty no VPS e gere logs/notification_drain_last.json recente e da mesma rodada.",
        ),
        _item(
            "Manifesto hashado da rodada de verificação quando exigido",
            (not require_verification_manifest) or verification_manifest_ok,
            {
                "require_verification_manifest": require_verification_manifest,
                "latest_receipt": verification_manifest_receipt,
                "freshness": verification_manifest_freshness,
                "run_id": verification_manifest_run_id,
                "hash_coherence": verification_manifest_hash_coherence,
            },
            "Rode python -m scripts.build_verification_manifest no VPS e gere logs/verification_manifest_last.json da mesma rodada, sem alterar os recibos depois.",
        ),
        _item(
            "Recibos obrigatórios coerentes no mesmo host de produção",
            (not required_receipts) or receipt_host_coherence["ok"],
            {
                "strict": strict,
                "required_receipt_count": len(required_receipts),
                "coherence": receipt_host_coherence,
            },
            "Rode novamente o verify_vps.sh na mesma máquina/ambiente de produção para regenerar todos os recibos obrigatórios na mesma rodada.",
        ),
        _item(
            "Recibos obrigatórios refletem a configuração isolada esperada",
            receipt_parameter_coherence["ok"],
            {
                "expected": {
                    "app_dir": expected_app_dir,
                    "app_user": expected_app_user,
                    "env_file": resolved_expected_env_file,
                    "api_base_url": expected_api_base_url,
                    "api_port": expected_api_port,
                },
                "coherence": receipt_parameter_coherence,
            },
            "Rode novamente o verify_vps.sh com APP_DIR/APP_USER/API corretos para regenerar recibos da configuração isolada esperada.",
        ),
    ]

    passed = [item for item in items if item.passed]
    blocked = [item for item in items if not item.passed]
    optional_requirements = set()
    if not require_canary:
        optional_requirements.add("Canário Telegram via outbox quando exigido")
    if not require_preflight:
        optional_requirements.add("Preflight de produção quando exigido")
    if not require_ops_protection:
        optional_requirements.add("Proteção HTTP dos endpoints operacionais quando exigida")
    if not require_systemd_runtime:
        optional_requirements.add("Runtime systemd isolado no VPS quando exigido")
    if not require_filesystem_isolation:
        optional_requirements.add("Ownership e permissões do app no VPS quando exigidos")
    if not require_process_runtime:
        optional_requirements.add("Processos e bind de runtime do VPS quando exigidos")
    if not require_notification_drain:
        optional_requirements.add("Drenagem da outbox quando exigida")
    if not require_verification_manifest:
        optional_requirements.add("Manifesto hashado da rodada de verificação quando exigido")
    blocked_requirements = {item.requirement for item in blocked}
    ready_for_local_handoff = not blocked or blocked_requirements.issubset(optional_requirements)
    return {
        "objective": (
            f"Construir e validar versão isolada do SUPER_TRADER_QUANT com {EXPECTED_ASSET_COUNT} ativos demo, "
            "memória de desfecho, execução 24/7 e alertas Telegram sem interferir no VPS."
        ),
        "strict": strict,
        "runtime": runtime,
        "require_canary": require_canary,
        "require_preflight": require_preflight,
        "require_ops_protection": require_ops_protection,
        "require_systemd_runtime": require_systemd_runtime,
        "require_filesystem_isolation": require_filesystem_isolation,
        "require_process_runtime": require_process_runtime,
        "require_notification_drain": require_notification_drain,
        "require_verification_manifest": require_verification_manifest,
        "expected_run_id": expected_run_id,
        "expected_app_dir": expected_app_dir,
        "expected_app_user": expected_app_user,
        "expected_env_file": resolved_expected_env_file,
        "expected_api_base_url": expected_api_base_url,
        "expected_api_port": expected_api_port,
        "run_id": expected_run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready_for_local_handoff": ready_for_local_handoff,
        "complete": not blocked,
        "summary": {
            "passed": len(passed),
            "blocked": len(blocked),
            "total": len(items),
        },
        "items": [item.__dict__ for item in items],
        "next_required_actions": [
            item.blocker for item in blocked if item.blocker
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera relatório de aceitação do objetivo SUPER_TRADER_QUANT.")
    parser.add_argument("--strict", action="store_true", help="Exige token Telegram e provider real.")
    parser.add_argument("--runtime", action="store_true", help="Exige heartbeat/runtime saudável.")
    parser.add_argument(
        "--require-canary",
        action="store_true",
        help="Marca o objetivo como bloqueado até o canário Telegram real ser rodado no VPS.",
    )
    parser.add_argument(
        "--require-preflight",
        action="store_true",
        help="Marca o objetivo como bloqueado até o preflight de produção real ser rodado no VPS.",
    )
    parser.add_argument(
        "--require-ops-protection",
        action="store_true",
        help="Marca o objetivo como bloqueado até a proteção HTTP dos endpoints /ops ser comprovada no VPS.",
    )
    parser.add_argument(
        "--require-systemd-runtime",
        action="store_true",
        help="Marca o objetivo como bloqueado até o runtime efetivo das units systemd ser comprovado no VPS.",
    )
    parser.add_argument(
        "--require-filesystem-isolation",
        action="store_true",
        help="Marca o objetivo como bloqueado até ownership e permissões do app serem comprovados no VPS.",
    )
    parser.add_argument(
        "--require-process-runtime",
        action="store_true",
        help="Marca o objetivo como bloqueado até usuário/cwd/cmdline e bind em loopback serem comprovados no VPS.",
    )
    parser.add_argument(
        "--require-notification-drain",
        action="store_true",
        help="Marca o objetivo como bloqueado até a drenagem da outbox ser comprovada no VPS com recibo próprio.",
    )
    parser.add_argument(
        "--require-verification-manifest",
        action="store_true",
        help="Marca o objetivo como bloqueado até existir um manifesto hashado coerente com os recibos obrigatórios da rodada.",
    )
    parser.add_argument("--expected-run-id", help="Exige que os recibos obrigatórios pertençam a uma mesma rodada de verificação.")
    parser.add_argument("--expected-app-dir", default=EXPECTED_VPS_APP_DIR)
    parser.add_argument("--expected-app-user", default=EXPECTED_VPS_APP_USER)
    parser.add_argument("--expected-env-file")
    parser.add_argument("--expected-api-base-url", default=EXPECTED_VPS_API_BASE_URL)
    parser.add_argument("--expected-api-port", type=int, default=EXPECTED_VPS_API_PORT)
    parser.add_argument("--json", action="store_true", help="Imprime JSON completo.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()

    report = build_acceptance_report(
        strict=args.strict,
        runtime=args.runtime,
        require_canary=args.require_canary,
        require_preflight=args.require_preflight,
        require_ops_protection=args.require_ops_protection,
        require_systemd_runtime=args.require_systemd_runtime,
        require_filesystem_isolation=args.require_filesystem_isolation,
        require_process_runtime=args.require_process_runtime,
        require_notification_drain=args.require_notification_drain,
        require_verification_manifest=args.require_verification_manifest,
        expected_run_id=args.expected_run_id,
        expected_app_dir=args.expected_app_dir,
        expected_app_user=args.expected_app_user,
        expected_env_file=args.expected_env_file,
        expected_api_base_url=args.expected_api_base_url,
        expected_api_port=args.expected_api_port,
    )
    if args.output:
        output_path = Path(args.output)
        write_json_receipt(output_path, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"complete: {report['complete']}")
        print(f"ready_for_local_handoff: {report['ready_for_local_handoff']}")
        print(f"summary: {report['summary']}")
        for item in report["items"]:
            print(f"- {item['status']}: {item['requirement']}")
            if item["blocker"]:
                print(f"  blocker: {item['blocker']}")
    raise SystemExit(0 if report["ready_for_local_handoff"] else 1)


if __name__ == "__main__":
    main()
