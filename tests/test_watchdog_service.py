from datetime import timedelta

from sqlmodel import SQLModel, Session, create_engine, select

from super_trader_quant.backend.app.demo_assets import EXPECTED_ASSET_COUNT, EXPECTED_ASSETS_BY_MARKET
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.memory import SetupMemory  # noqa: F401
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal  # noqa: F401
from super_trader_quant.backend.app.services import watchdog_service
from super_trader_quant.backend.app.time_utils import utc_now_naive


def _add_expected_assets(session: Session) -> None:
    country_by_market = {"BR": "Brasil", "US": "EUA", "UK": "Reino Unido"}
    for market, expected_count in EXPECTED_ASSETS_BY_MARKET.items():
        for index in range(expected_count):
            country = country_by_market[market]
            session.add(Asset(symbol=f"{market}{index:02d}", market=market, country=country))
    session.commit()


def test_watchdog_report_ok_when_runtime_is_healthy(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    heartbeat = {
        "last_event": "scan_job",
        "last_seen_at": utc_now_naive().isoformat(),
    }
    monkeypatch.setattr(watchdog_service, "read_scheduler_heartbeat", lambda: heartbeat)
    monkeypatch.setattr(watchdog_service.settings, "telegram_bot_token", "token")
    monkeypatch.setattr(watchdog_service.settings, "default_provider", "yfinance")

    with Session(engine) as session:
        _add_expected_assets(session)
        report = watchdog_service.collect_watchdog_report(session, strict=True)

    assert report["ok"] is True
    assert report["issues"] == []
    assert report["active_assets_by_market"] == EXPECTED_ASSETS_BY_MARKET


def test_watchdog_report_accepts_br_only_telegram_route(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    heartbeat = {
        "last_event": "scan_job",
        "last_seen_at": utc_now_naive().isoformat(),
    }
    monkeypatch.setattr(watchdog_service, "read_scheduler_heartbeat", lambda: heartbeat)
    monkeypatch.setattr(watchdog_service.settings, "telegram_bot_token", "")
    monkeypatch.setattr(watchdog_service.settings, "telegram_chat_ids", "")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_bot_token", "br-token")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_chat_ids", "111111111")
    monkeypatch.setattr(watchdog_service.settings, "default_provider", "yfinance")

    with Session(engine) as session:
        _add_expected_assets(session)
        report = watchdog_service.collect_watchdog_report(session, strict=True)

    assert report["ok"] is True
    assert report["issues"] == []


def test_watchdog_report_flags_stale_heartbeat_and_bad_asset_split(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    heartbeat = {
        "last_event": "startup_begin",
        "last_seen_at": (utc_now_naive() - timedelta(hours=3)).isoformat(),
    }
    monkeypatch.setattr(watchdog_service, "read_scheduler_heartbeat", lambda: heartbeat)

    with Session(engine) as session:
        session.add(Asset(symbol="AAPL", market="US", country="EUA"))
        session.commit()
        report = watchdog_service.collect_watchdog_report(session)

    codes = {issue["code"] for issue in report["issues"]}
    assert report["ok"] is False
    assert "active_asset_count" in codes
    assert "asset_split" in codes
    assert "scheduler_startup_stuck" in codes
    assert "scheduler_heartbeat_stale" in codes


def test_watchdog_report_allows_startup_within_grace_window(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    heartbeat = {
        "last_event": "startup_begin",
        "last_seen_at": (utc_now_naive() - timedelta(seconds=30)).isoformat(),
    }
    monkeypatch.setattr(watchdog_service, "read_scheduler_heartbeat", lambda: heartbeat)
    monkeypatch.setattr(watchdog_service.settings, "scheduler_startup_grace_seconds", 120)

    with Session(engine) as session:
        _add_expected_assets(session)
        report = watchdog_service.collect_watchdog_report(session)

    codes = {issue["code"] for issue in report["issues"]}
    assert "scheduler_startup_stuck" not in codes
    assert "scheduler_heartbeat_stale" not in codes
    assert report["ok"] is True


def test_watchdog_report_flags_resource_guard_issues(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    heartbeat = {
        "last_event": "scan_job",
        "last_seen_at": utc_now_naive().isoformat(),
    }
    monkeypatch.setattr(watchdog_service, "read_scheduler_heartbeat", lambda: heartbeat)
    monkeypatch.setattr(
        watchdog_service,
        "collect_ops_metrics",
        lambda session: {
            "stale_open_signals": 0,
            "stale_pending_notifications": 0,
            "failed_notifications": 0,
            "resources": {
                "low_disk_paths": ["backup_dir"],
                "free_disk_mb_by_path": {"backup_dir": 1.0},
                "database_size_exceeded": True,
                "database_size_mb": 4096,
                "max_database_size_mb": 2048,
            },
        },
    )

    with Session(engine) as session:
        _add_expected_assets(session)
        report = watchdog_service.collect_watchdog_report(session)

    codes = {issue["code"] for issue in report["issues"]}
    assert "low_disk_space" in codes
    assert "database_size_exceeded" in codes


def test_watchdog_notification_is_deduplicated(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(watchdog_service.settings, "telegram_bot_token", "token")
    monkeypatch.setattr(watchdog_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_bot_token", "")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_chat_ids", "")
    monkeypatch.setattr(watchdog_service.settings, "watchdog_alert_dedupe_minutes", 60)
    report = {
        "ok": False,
        "checked_at": utc_now_naive().isoformat(),
        "issues": [{"code": "scheduler_heartbeat_missing", "message": "sem heartbeat"}],
        "active_assets": 0,
        "active_assets_by_market": {"BR": 0, "US": 0, "UK": 0},
        "scheduler_heartbeat_age_seconds": None,
    }

    with Session(engine) as session:
        first = watchdog_service.enqueue_watchdog_notification(session, report)
        second = watchdog_service.enqueue_watchdog_notification(session, report)
        session.commit()
        notifications = session.exec(select(Notification)).all()

    assert len(first) == 1
    assert len(second) == 1
    assert len(notifications) == 1
    assert notifications[0].kind == "ops_watchdog"
    assert "Watchdog ALERTA" in notifications[0].message


def test_watchdog_notification_uses_br_route_when_only_br_is_configured(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(watchdog_service.settings, "telegram_bot_token", "")
    monkeypatch.setattr(watchdog_service.settings, "telegram_chat_ids", "")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_bot_token", "br-token")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_chat_ids", "111111111")
    report = {
        "ok": False,
        "checked_at": utc_now_naive().isoformat(),
        "issues": [{"code": "memory_inconsistent", "message": "memoria inconsistente"}],
        "active_assets": EXPECTED_ASSET_COUNT,
        "active_assets_by_market": EXPECTED_ASSETS_BY_MARKET,
        "scheduler_heartbeat_age_seconds": 1.0,
    }

    with Session(engine) as session:
        queued = watchdog_service.enqueue_watchdog_notification(session, report)
        session.commit()
        notifications = session.exec(select(Notification)).all()

    assert len(queued) == 1
    assert len(notifications) == 1
    assert notifications[0].route == "br"
    assert notifications[0].chat_id == "111111111"


def test_watchdog_ok_notification_is_optional(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(watchdog_service.settings, "telegram_bot_token", "token")
    monkeypatch.setattr(watchdog_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_bot_token", "")
    monkeypatch.setattr(watchdog_service.settings, "telegram_br_chat_ids", "")
    report = {
        "ok": True,
        "checked_at": utc_now_naive().isoformat(),
        "issues": [],
        "active_assets": EXPECTED_ASSET_COUNT,
        "active_assets_by_market": EXPECTED_ASSETS_BY_MARKET,
        "scheduler_heartbeat_age_seconds": 1.0,
    }

    with Session(engine) as session:
        skipped = watchdog_service.enqueue_watchdog_notification(session, report)
        queued = watchdog_service.enqueue_watchdog_notification(session, report, notify_ok=True)
        session.commit()
        notifications = session.exec(select(Notification)).all()

    assert skipped == []
    assert len(queued) == 1
    assert len(notifications) == 1
    assert "Watchdog OK" in notifications[0].message
