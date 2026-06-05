from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from sqlmodel import Session, select
from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.demo_assets import EXPECTED_ASSET_COUNT, EXPECTED_ASSETS_BY_MARKET
from super_trader_quant.backend.app.engine.memory_engine import memory_consistency_report
from super_trader_quant.backend.app.services.heartbeat_service import read_scheduler_heartbeat
from super_trader_quant.backend.app.services.ops_metrics_service import collect_ops_metrics
from super_trader_quant.backend.app.services.scheduler_service import build_scheduler
from super_trader_quant.backend.app.time_utils import utc_now_naive
from scripts.validate_deploy_artifacts import validate_deploy_artifacts


def build_report(strict: bool = False, runtime: bool = False) -> dict[str, object]:
    init_db()
    with Session(engine) as session:
        assets = session.exec(select(Asset)).all()
        active_assets = [asset for asset in assets if asset.active]
        active_assets_by_market = {
            market: sum(asset.market == market for asset in active_assets)
            for market in EXPECTED_ASSETS_BY_MARKET
        }
        ops_metrics = collect_ops_metrics(session)
        memory_report = memory_consistency_report(session)

    scheduler_jobs = sorted(job.id for job in build_scheduler().get_jobs())
    deploy_report = validate_deploy_artifacts()
    heartbeat = read_scheduler_heartbeat()
    heartbeat_age_seconds = None
    if heartbeat and heartbeat.get("last_seen_at"):
        heartbeat_age_seconds = (
            utc_now_naive() - datetime.fromisoformat(str(heartbeat["last_seen_at"]))
        ).total_seconds()
    heartbeat_startup_within_grace = (
        heartbeat is not None
        and heartbeat.get("last_event") == "startup_begin"
        and heartbeat_age_seconds is not None
        and heartbeat_age_seconds <= settings.scheduler_startup_grace_seconds
    )
    heartbeat_max_age_seconds = max(
        settings.scan_interval_minutes,
        settings.outcome_check_interval_minutes,
    ) * 60 * 2
    primary_route_enabled = bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id_list)
    br_route_enabled = bool(settings.telegram_br_bot_token) and bool(settings.telegram_br_chat_id_list)
    checks = {
        "database_path_parent_exists": Path(settings.database_url.replace("sqlite:///", "")).parent.exists()
        if settings.database_url.startswith("sqlite:///")
        else True,
        "log_dir_exists": settings.resolved_log_dir.exists(),
        "scheduler_lock_parent_exists": settings.resolved_scheduler_lock_path.parent.exists(),
        "backup_dir_exists": settings.resolved_backup_dir.exists(),
        "deploy_artifacts_valid": deploy_report["ok"],
        "active_asset_count_matches_expected": len(active_assets) == EXPECTED_ASSET_COUNT,
        "active_asset_split_matches_expected": active_assets_by_market == EXPECTED_ASSETS_BY_MARKET,
        "scheduler_jobs_ok": scheduler_jobs == ["maintenance_job", "notification_job", "resolve_job", "scan_job"],
        "telegram_chat_ids_present": bool(settings.telegram_chat_id_list or settings.telegram_br_chat_id_list),
        "telegram_token_present": bool(settings.telegram_bot_token or settings.telegram_br_bot_token),
        "telegram_primary_route_consistent": (
            (not settings.telegram_bot_token and not settings.telegram_chat_id_list)
            or primary_route_enabled
        ),
        "telegram_br_route_consistent": (
            (not settings.telegram_br_bot_token and not settings.telegram_br_chat_id_list)
            or br_route_enabled
        ),
        "telegram_any_route_configured": primary_route_enabled or br_route_enabled,
        "ops_admin_token_present": bool(settings.ops_admin_token),
        "provider_not_simulated": settings.default_provider != "simulated",
        "scheduler_heartbeat_present": heartbeat is not None,
        "scheduler_heartbeat_not_starting": heartbeat is not None
        and (
            heartbeat.get("last_event") != "startup_begin"
            or heartbeat_startup_within_grace
        ),
        "scheduler_heartbeat_fresh": heartbeat_age_seconds is not None
        and heartbeat_age_seconds <= heartbeat_max_age_seconds,
        "no_stale_open_signals": ops_metrics["stale_open_signals"] == 0,
        "no_stale_pending_notifications": ops_metrics["stale_pending_notifications"] == 0,
        "memory_consistent": memory_report["is_consistent"],
    }
    required = [
        "database_path_parent_exists",
        "log_dir_exists",
        "scheduler_lock_parent_exists",
        "backup_dir_exists",
        "deploy_artifacts_valid",
        "active_asset_count_matches_expected",
        "active_asset_split_matches_expected",
        "scheduler_jobs_ok",
        "telegram_chat_ids_present",
        "telegram_primary_route_consistent",
        "telegram_br_route_consistent",
        "telegram_any_route_configured",
    ]
    if strict:
        required.extend(["telegram_token_present", "ops_admin_token_present", "provider_not_simulated"])
    if runtime:
        required.extend(
            [
                "scheduler_heartbeat_present",
                "scheduler_heartbeat_not_starting",
                "scheduler_heartbeat_fresh",
                "no_stale_open_signals",
                "no_stale_pending_notifications",
                "memory_consistent",
            ]
        )

    return {
        "app_env": settings.app_env,
        "database_url": settings.database_url,
        "default_provider": settings.default_provider,
        "scan_timeframe": settings.scan_timeframe,
        "scan_interval_minutes": settings.scan_interval_minutes,
        "api_bind": f"{settings.api_host}:{settings.api_port}",
        "scheduler_lock_path": str(settings.resolved_scheduler_lock_path),
        "backup_dir": str(settings.resolved_backup_dir),
        "active_asset_count": len(active_assets),
        "expected_active_asset_count": EXPECTED_ASSET_COUNT,
        "active_assets_by_market": active_assets_by_market,
        "expected_active_assets_by_market": EXPECTED_ASSETS_BY_MARKET,
        "telegram_chat_ids": settings.telegram_chat_id_list,
        "telegram_br_chat_ids": settings.telegram_br_chat_id_list,
        "telegram_primary_enabled": primary_route_enabled,
        "telegram_br_enabled": br_route_enabled,
        "scheduler_jobs": scheduler_jobs,
        "scheduler_heartbeat": heartbeat,
        "scheduler_heartbeat_age_seconds": heartbeat_age_seconds,
        "scheduler_startup_within_grace": heartbeat_startup_within_grace,
        "scheduler_startup_grace_seconds": settings.scheduler_startup_grace_seconds,
        "ops_metrics": ops_metrics,
        "memory_consistency": memory_report,
        "deploy_artifacts": deploy_report,
        "checks": checks,
        "ready": all(checks[name] for name in required),
        "strict": strict,
        "runtime": runtime,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--runtime", action="store_true")
    args = parser.parse_args()
    report = build_report(strict=args.strict, runtime=args.runtime)
    for key, value in report.items():
        print(f"{key}: {value}")
    raise SystemExit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
