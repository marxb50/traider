from datetime import datetime, timedelta
import pandas as pd
from sqlmodel import Session, SQLModel, create_engine, select
from super_trader_quant.backend.app.engine.scanner_engine import resolve_open_signals
from super_trader_quant.backend.app.models.memory import SetupMemory
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal


class ResolutionProvider:
    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        start = datetime(2026, 1, 1)
        return pd.DataFrame([
            {"timestamp": start, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
            {"timestamp": start + timedelta(days=1), "open": 101, "high": 111, "low": 100, "close": 109, "volume": 1},
        ])


class ShortResolutionProvider:
    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        start = datetime(2026, 1, 1)
        return pd.DataFrame([
            {"timestamp": start, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
            {"timestamp": start + timedelta(days=1), "open": 100, "high": 102, "low": 89, "close": 91, "volume": 1},
        ])


def test_open_signal_is_resolved_and_memory_created():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        signal = Signal(
            asset_symbol="PETR4.SA",
            market="BR",
            strategy="IFR2",
            timeframe="D1",
            signal_time=datetime(2026, 1, 1),
            entry=100,
            stop=95,
            target=110,
            holding_period_bars=2,
        )
        session.add(signal)
        session.commit()
        resolved = resolve_open_signals(session, ResolutionProvider())
        assert len(resolved) == 1
        assert resolved[0].status == "success"
        memory = session.exec(select(SetupMemory)).one()
        assert memory.total_signals == 1
        assert memory.successes == 1
        assert session.exec(select(Notification)).all() == []


def test_open_short_signal_is_resolved_with_positive_pnl():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        signal = Signal(
            asset_symbol="VALE3.SA",
            market="BR",
            strategy="Donchian",
            timeframe="D1",
            signal_time=datetime(2026, 1, 1),
            side="short",
            entry=100,
            stop=105,
            target=90,
            holding_period_bars=2,
        )
        session.add(signal)
        session.commit()

        resolved = resolve_open_signals(session, ShortResolutionProvider())

        assert len(resolved) == 1
        assert resolved[0].status == "success"
        assert resolved[0].side == "short"
        assert resolved[0].exit_price == 90
        assert round(resolved[0].pnl_pct, 3) == 11.111
        memory = session.exec(select(SetupMemory)).one()
        assert memory.total_signals == 1
        assert memory.successes == 1
