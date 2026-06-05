from __future__ import annotations

import hashlib
from datetime import datetime
from sqlmodel import Session, select

from ..config import settings
from ..demo_assets import EXPECTED_ASSET_COUNT, EXPECTED_ASSETS_BY_MARKET
from ..engine.memory_engine import memory_consistency_report
from ..models.asset import Asset
from ..models.notification import Notification
from ..services.heartbeat_service import read_scheduler_heartbeat
from ..time_utils import utc_now_naive
from .notification_service import enqueue_notification
from .telegram_service import BRAZIL_ROUTE, PRIMARY_ROUTE, is_telegram_route_partially_configured


def _configured_watchdog_routes() -> list[str]:
    return [
        route
        for route in (PRIMARY_ROUTE, BRAZIL_ROUTE)
        if is_telegram_route_partially_configured(route)
    ]
from .ops_metrics_service import collect_ops_metrics


def _heartbeat_age_seconds(heartbeat: dict[str, object] | None) -> float | None:
    if not heartbeat or not heartbeat.get("last_seen_at"):
        return None
    return (utc_now_naive() - datetime.fromisoformat(str(heartbeat["last_seen_at"]))).total_seconds()


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def collect_watchdog_report(session: Session, *, strict: bool = False) -> dict[str, object]:
    assets = session.exec(select(Asset)).all()
    active_assets = [asset for asset in assets if asset.active]
    active_assets_by_market = {
        market: sum(asset.market == market for asset in active_assets)
        for market in EXPECTED_ASSETS_BY_MARKET
    }
    ops_metrics = collect_ops_metrics(session)
    memory_report = memory_consistency_report(session)
    heartbeat = read_scheduler_heartbeat()
    heartbeat_age_seconds = _heartbeat_age_seconds(heartbeat)
    heartbeat_max_age_seconds = max(
        settings.scan_interval_minutes,
        settings.outcome_check_interval_minutes,
    ) * 60 * 2

    issues: list[dict[str, str]] = []
    if len(active_assets) != EXPECTED_ASSET_COUNT:
        issues.append(_issue("active_asset_count", f"Ativos ativos: {len(active_assets)}; esperado: {EXPECTED_ASSET_COUNT}."))
    if active_assets_by_market != EXPECTED_ASSETS_BY_MARKET:
        issues.append(_issue("asset_split", f"Split por mercado inválido: {active_assets_by_market}; esperado: {EXPECTED_ASSETS_BY_MARKET}."))
    if heartbeat is None:
        issues.append(_issue("scheduler_heartbeat_missing", "Heartbeat do scheduler ausente."))
    elif (
        heartbeat.get("last_event") == "startup_begin"
        and heartbeat_age_seconds is not None
        and heartbeat_age_seconds > settings.scheduler_startup_grace_seconds
    ):
        issues.append(_issue("scheduler_startup_stuck", "Scheduler parou no início do ciclo de startup."))
    if heartbeat_age_seconds is None or heartbeat_age_seconds > heartbeat_max_age_seconds:
        issues.append(
            _issue(
                "scheduler_heartbeat_stale",
                f"Heartbeat velho ou inválido: {heartbeat_age_seconds}s; limite: {heartbeat_max_age_seconds}s.",
            )
        )
    if ops_metrics["stale_open_signals"]:
        issues.append(_issue("stale_open_signals", f"Sinais abertos velhos: {ops_metrics['stale_open_signals']}."))
    if ops_metrics["stale_pending_notifications"]:
        issues.append(
            _issue(
                "stale_pending_notifications",
                f"Alertas Telegram pendentes velhos: {ops_metrics['stale_pending_notifications']}.",
            )
        )
    if ops_metrics["failed_notifications"]:
        issues.append(_issue("failed_notifications", f"Alertas Telegram com falha: {ops_metrics['failed_notifications']}."))
    resources = ops_metrics.get("resources", {})
    if resources.get("low_disk_paths"):
        issues.append(
            _issue(
                "low_disk_space",
                f"Pouco espaço livre em {resources['low_disk_paths']}; livres MB: {resources.get('free_disk_mb_by_path')}.",
            )
        )
    if resources.get("database_size_exceeded"):
        issues.append(
            _issue(
                "database_size_exceeded",
                f"Banco {resources.get('database_size_mb')} MB acima do limite {resources.get('max_database_size_mb')} MB.",
            )
        )
    if not memory_report["is_consistent"]:
        issues.append(_issue("memory_inconsistent", f"Memória inconsistente: {memory_report}."))
    if strict and not _configured_watchdog_routes():
        issues.append(_issue("telegram_route_missing", "Nenhuma rota Telegram configurada."))
    if strict and settings.default_provider == "simulated":
        issues.append(_issue("provider_simulated", "DEFAULT_PROVIDER ainda está em simulated."))

    return {
        "ok": not issues,
        "strict": strict,
        "checked_at": utc_now_naive().isoformat(),
        "issues": issues,
        "active_assets": len(active_assets),
        "expected_active_assets": EXPECTED_ASSET_COUNT,
        "active_assets_by_market": active_assets_by_market,
        "expected_active_assets_by_market": EXPECTED_ASSETS_BY_MARKET,
        "scheduler_heartbeat": heartbeat,
        "scheduler_heartbeat_age_seconds": heartbeat_age_seconds,
        "scheduler_heartbeat_max_age_seconds": heartbeat_max_age_seconds,
        "scheduler_startup_grace_seconds": settings.scheduler_startup_grace_seconds,
        "ops_metrics": ops_metrics,
        "memory_consistency": memory_report,
    }


def format_watchdog_message(report: dict[str, object]) -> str:
    status = "OK" if report["ok"] else "ALERTA"
    lines = [
        f"[SUPER_TRADER_QUANT] Watchdog {status}",
        f"checado em: {report['checked_at']} UTC",
        f"ativos: {report['active_assets']} | split: {report['active_assets_by_market']}",
        f"heartbeat_age_s: {report['scheduler_heartbeat_age_seconds']}",
        "SIMULAÇÃO — NÃO É CONTA REAL",
    ]
    issues = report.get("issues") or []
    if issues:
        lines.append("problemas:")
        for issue in issues:
            lines.append(f"- {issue['code']}: {issue['message']}")
    return "\n".join(lines)


def enqueue_watchdog_notification(
    session: Session,
    report: dict[str, object],
    *,
    notify_ok: bool = False,
) -> list[Notification]:
    if report["ok"] and not notify_ok:
        return []
    issue_codes = [issue["code"] for issue in report.get("issues", [])] or ["ok"]
    issue_fingerprint = hashlib.sha1("|".join(sorted(issue_codes)).encode("utf-8")).hexdigest()[:12]
    dedupe_seconds = max(settings.watchdog_alert_dedupe_minutes, 1) * 60
    bucket = int(utc_now_naive().timestamp() // dedupe_seconds)
    status_key = "ok" if report["ok"] else "alert"
    return enqueue_notification(
        session,
        kind="ops_watchdog",
        dedupe_key=f"ops_watchdog:{status_key}:{issue_fingerprint}:{bucket}",
        message=format_watchdog_message(report),
        routes=_configured_watchdog_routes(),
    )
