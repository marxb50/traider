from datetime import timedelta
from sqlmodel import SQLModel, Session, create_engine
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal
from super_trader_quant.backend.app.services import ops_metrics_service
from super_trader_quant.backend.app.time_utils import utc_now_naive


def test_ops_metrics_detect_stale_items(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ops_metrics_service.settings, "max_open_signal_age_days", 7)
    monkeypatch.setattr(ops_metrics_service.settings, "max_pending_notification_age_minutes", 10)
    now = utc_now_naive()

    with Session(engine) as session:
        session.add(Asset(symbol="AAPL", market="US", country="EUA"))
        session.add(
            Signal(
                asset_symbol="AAPL",
                market="US",
                strategy="IFR2",
                timeframe="D1",
                signal_time=now - timedelta(days=8),
                entry=100,
                stop=95,
                target=110,
            )
        )
        session.add(
            Notification(
                kind="signal_opened",
                dedupe_key="signal_opened:stale",
                message="teste",
                created_at=now - timedelta(minutes=11),
            )
        )
        session.add(
            Notification(
                kind="signal_opened",
                dedupe_key="signal_opened:suppressed",
                message="suprimida",
                status="suppressed",
                created_at=now - timedelta(minutes=20),
            )
        )
        session.commit()

        metrics = ops_metrics_service.collect_ops_metrics(session)

    assert metrics["stale_open_signals"] == 1
    assert metrics["stale_pending_notifications"] == 1
    assert metrics["suppressed_notifications"] == 1
    assert metrics["resources"]["resource_guard_ok"] in {True, False}
