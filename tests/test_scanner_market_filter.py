from datetime import datetime, timedelta

import pandas as pd
from sqlmodel import SQLModel, Session, create_engine, select

from super_trader_quant.backend.app.engine import scanner_engine
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal


class _AlwaysSignalStrategy:
    name = "AlwaysSignal"

    def latest_signal(self, df):
        last = df.iloc[-1]
        return {
            "signal_time": last["timestamp"],
            "entry": float(last["close"]),
            "stop": float(last["close"]) * 0.99,
            "target": float(last["close"]) * 1.01,
            "holding_period_bars": 5,
        }


class _BatchProvider:
    def fetch_many_history(self, symbols, timeframe="D1", period="1y"):
        frame = pd.DataFrame(
            [
                {
                    "timestamp": datetime(2026, 1, 1),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1.0,
                }
            ]
        )
        return {symbol: frame.copy() for symbol in symbols}


class _ResolveProvider:
    def fetch_many_history(self, symbols, timeframe="D1", period="1y"):
        base = datetime(2026, 1, 1)
        frame = pd.DataFrame(
            [
                {
                    "timestamp": base,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1.0,
                },
                {
                    "timestamp": base + timedelta(days=1),
                    "open": 101.0,
                    "high": 120.0,
                    "low": 100.0,
                    "close": 118.0,
                    "volume": 1.0,
                },
            ]
        )
        return {symbol: frame.copy() for symbol in symbols}


def test_scan_assets_respects_market_filter(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(scanner_engine.settings, "scan_markets", "BR")
    monkeypatch.setattr(scanner_engine, "STRATEGY_REGISTRY", {"always": _AlwaysSignalStrategy})

    with Session(engine) as session:
        session.add(Asset(symbol="PETR4.SA", market="BR", country="Brasil"))
        session.add(Asset(symbol="AAPL", market="US", country="EUA"))
        session.commit()

        created = scanner_engine.scan_assets(session, _BatchProvider())

    assert len(created) == 1
    assert created[0].asset_symbol == "PETR4.SA"
    assert created[0].market == "BR"


def test_resolve_open_signals_suppresses_notification_for_disallowed_market(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(scanner_engine.settings, "scan_markets", "BR")

    signal_time = datetime(2026, 1, 1)

    with Session(engine) as session:
        session.add(
            Signal(
                asset_symbol="AAPL",
                market="US",
                strategy="Setup_123",
                timeframe="D1",
                signal_time=signal_time,
                entry=100.0,
                stop=95.0,
                target=110.0,
                holding_period_bars=5,
            )
        )
        session.commit()

        resolved = scanner_engine.resolve_open_signals(session, _ResolveProvider())

        notifications = session.exec(select(Notification)).all()

    assert len(resolved) == 1
    assert resolved[0].status == "success"
    assert notifications == []
