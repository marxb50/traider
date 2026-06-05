from datetime import timedelta
from types import SimpleNamespace

from sqlmodel import SQLModel, Session, create_engine

from scripts import check_deploy_readiness
from super_trader_quant.backend.app.demo_assets import EXPECTED_ASSETS_BY_MARKET
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.time_utils import utc_now_naive


def _seed_assets(session: Session) -> None:
    country_by_market = {"BR": "Brasil", "US": "EUA", "UK": "Reino Unido"}
    for market, expected_count in EXPECTED_ASSETS_BY_MARKET.items():
        for index in range(expected_count):
            country = country_by_market[market]
            session.add(Asset(symbol=f"{market}{index:02d}", market=market, country=country, active=True))
    session.commit()


def _patch_healthy_dependencies(monkeypatch, engine, heartbeat):
    monkeypatch.setattr(check_deploy_readiness, "engine", engine)
    monkeypatch.setattr(check_deploy_readiness, "init_db", lambda: None)
    monkeypatch.setattr(
        check_deploy_readiness,
        "build_scheduler",
        lambda: SimpleNamespace(
            get_jobs=lambda: [
                SimpleNamespace(id="maintenance_job"),
                SimpleNamespace(id="notification_job"),
                SimpleNamespace(id="resolve_job"),
                SimpleNamespace(id="scan_job"),
            ]
        ),
    )
    monkeypatch.setattr(check_deploy_readiness, "validate_deploy_artifacts", lambda: {"ok": True, "issues": []})
    monkeypatch.setattr(check_deploy_readiness, "read_scheduler_heartbeat", lambda: heartbeat)
    monkeypatch.setattr(
        check_deploy_readiness,
        "collect_ops_metrics",
        lambda session: {"stale_open_signals": 0, "stale_pending_notifications": 0},
    )
    monkeypatch.setattr(
        check_deploy_readiness,
        "memory_consistency_report",
        lambda session: {"is_consistent": True},
    )
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_br_bot_token", "br-token-456")
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_br_chat_ids", "111111111")
    monkeypatch.setattr(check_deploy_readiness.settings, "ops_admin_token", "ops-token-123")
    monkeypatch.setattr(check_deploy_readiness.settings, "default_provider", "yfinance")
    monkeypatch.setattr(check_deploy_readiness.settings, "scheduler_startup_grace_seconds", 120)


def test_readiness_accepts_startup_begin_within_grace(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_assets(session)

    heartbeat = {
        "last_event": "startup_begin",
        "last_seen_at": (utc_now_naive() - timedelta(seconds=30)).isoformat(),
    }
    _patch_healthy_dependencies(monkeypatch, engine, heartbeat)

    report = check_deploy_readiness.build_report(strict=True, runtime=True)

    assert report["checks"]["scheduler_heartbeat_not_starting"] is True
    assert report["scheduler_startup_within_grace"] is True
    assert report["ready"] is True


def test_readiness_blocks_startup_begin_after_grace(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_assets(session)

    heartbeat = {
        "last_event": "startup_begin",
        "last_seen_at": (utc_now_naive() - timedelta(seconds=300)).isoformat(),
    }
    _patch_healthy_dependencies(monkeypatch, engine, heartbeat)

    report = check_deploy_readiness.build_report(strict=True, runtime=True)

    assert report["checks"]["scheduler_heartbeat_not_starting"] is False
    assert report["scheduler_startup_within_grace"] is False
    assert report["ready"] is False


def test_readiness_accepts_br_only_route(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_assets(session)

    heartbeat = {
        "last_event": "notification_job",
        "last_seen_at": utc_now_naive().isoformat(),
    }
    _patch_healthy_dependencies(monkeypatch, engine, heartbeat)
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_bot_token", "")
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_chat_ids", "")
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_br_bot_token", "br-token-456")
    monkeypatch.setattr(check_deploy_readiness.settings, "telegram_br_chat_ids", "111111111,222222222")

    report = check_deploy_readiness.build_report(strict=True, runtime=True)

    assert report["checks"]["telegram_chat_ids_present"] is True
    assert report["checks"]["telegram_token_present"] is True
    assert report["checks"]["telegram_primary_route_consistent"] is True
    assert report["checks"]["telegram_br_route_consistent"] is True
    assert report["checks"]["telegram_any_route_configured"] is True
    assert report["telegram_primary_enabled"] is False
    assert report["telegram_br_enabled"] is True
    assert report["ready"] is True
