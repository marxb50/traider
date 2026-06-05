from datetime import datetime, timedelta
import pandas as pd
from sqlmodel import SQLModel, Session, create_engine, select
from super_trader_quant.backend.app.engine import scanner_engine
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.memory import SetupMemory
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal


class TwoPhaseProvider:
    def __init__(self):
        self.calls = 0
        start = datetime(2026, 1, 1)
        baseline = [
            {
                "timestamp": start + timedelta(days=i),
                "open": 100 + i * 0.1,
                "high": 101 + i * 0.1,
                "low": 99 + i * 0.1,
                "close": 100 + i * 0.1,
                "volume": 1,
            }
            for i in range(25)
        ]
        signal_bar = {
            "timestamp": start + timedelta(days=25),
            "open": 101,
            "high": 104,
            "low": 95,
            "close": 103,
            "volume": 1,
        }
        resolution_bar = {
            "timestamp": start + timedelta(days=26),
            "open": 104,
            "high": 120,
            "low": 103,
            "close": 118,
            "volume": 1,
        }
        self.scan_df = pd.DataFrame([*baseline, signal_bar])
        self.resolve_df = pd.DataFrame([*baseline, signal_bar, resolution_bar])

    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        self.calls += 1
        return self.scan_df.copy() if self.calls == 1 else self.resolve_df.copy()


def test_scan_then_resolve_updates_memory(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    provider = TwoPhaseProvider()
    monkeypatch.setattr(scanner_engine.settings, "signal_alert_min_level", "red")
    monkeypatch.setattr(scanner_engine.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(scanner_engine.settings, "telegram_chat_ids", "111111111")

    with Session(engine) as session:
        session.add(Asset(symbol="TEST3.SA", market="BR", country="Brasil"))
        session.commit()

        created = scanner_engine.scan_assets(session, provider, symbols=["TEST3.SA"])
        assert created
        assert session.exec(select(Signal)).all()

        resolved = scanner_engine.resolve_open_signals(session, provider)
        assert resolved
        assert all(signal.status in {"success", "failure", "expired"} for signal in resolved)

        memories = session.exec(select(SetupMemory)).all()
        assert memories
        assert sum(memory.total_signals for memory in memories) == len(resolved)
        notifications = session.exec(select(Notification)).all()

    assert any(notification.kind == "signal_opened" for notification in notifications)
    assert any(notification.kind == "signal_resolved" for notification in notifications)
