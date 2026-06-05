from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from super_trader_quant.backend.app.engine.scanner_engine import resolve_open_signals
from super_trader_quant.backend.app.models.memory import SetupMemory
from super_trader_quant.backend.app.models.signal import Signal
from super_trader_quant.backend.app import engine as engine_pkg


class NoFollowupProvider:
    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        return pd.DataFrame(
            [
                {
                    "timestamp": datetime(2026, 1, 1),
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 97,
                    "volume": 1,
                }
            ]
        )


def test_stale_open_signal_without_post_signal_data_expires(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    now = datetime(2026, 2, 15)
    monkeypatch.setattr(engine_pkg.scanner_engine.settings, "max_open_signal_age_days", 7)
    monkeypatch.setattr(engine_pkg.scanner_engine, "utc_now_naive", lambda: now)

    with Session(engine) as session:
        signal = Signal(
            asset_symbol="CRH.L",
            market="UK",
            strategy="IFR2",
            timeframe="D1",
            signal_time=datetime(2026, 1, 1),
            detected_at=now - timedelta(days=30),
            entry=100,
            stop=95,
            target=110,
            holding_period_bars=5,
        )
        session.add(signal)
        session.commit()

        resolved = resolve_open_signals(session, NoFollowupProvider())

        assert len(resolved) == 1
        assert resolved[0].status == "expired"
        assert resolved[0].exit_price == 97
        assert resolved[0].pnl_pct == pytest.approx(-3)
        assert resolved[0].notes == "expired_without_post_signal_data"

        memory = session.exec(select(SetupMemory)).one()
        assert memory.total_signals == 1
        assert memory.expired == 1
