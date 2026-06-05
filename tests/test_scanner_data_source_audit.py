from datetime import datetime, timedelta

import pandas as pd
from sqlmodel import SQLModel, Session, create_engine, select

from super_trader_quant.backend.app.engine import scanner_engine
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.models.signal import Signal
from super_trader_quant.backend.app.services.signal_quality_service import SignalQuality
from super_trader_quant.backend.app.strategies.base import BaseStrategy


class AlwaysSignalStrategy(BaseStrategy):
    name = "AlwaysSignal"
    holding_period_bars = 3

    def prepare(self, df):
        prepared = df.copy()
        prepared["signal"] = False
        prepared.loc[prepared.index[-1], "signal"] = True
        prepared["stop"] = prepared["close"] * 0.98
        prepared["target"] = prepared["close"] * 1.04
        return prepared


class PrimaryProvider:
    name = "yfinance"

    def fetch_many_history(self, symbols, timeframe="D1", period="1y"):
        return {symbol: _frame(close=100.0) for symbol in symbols}


class DivergentConfirmationProvider:
    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        return _frame(close=104.0)


def _frame(close: float):
    start = datetime(2026, 6, 1)
    return pd.DataFrame(
        [
            {
                "timestamp": start + timedelta(days=index),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1,
            }
            for index in range(30)
        ]
    )


def _strong_quality(_df, _strategy, _payload):
    return SignalQuality(
        level="green",
        score=88.0,
        probability_pct=70.0,
        sample_size=20,
        successes=14,
        failures=3,
        expired=3,
        avg_pnl_pct=1.1,
        avg_bars_to_target=2.0,
        risk_reward=2.0,
        target_pct=4.0,
        stop_pct=-2.0,
        reason="historico forte",
    )


def test_scanner_blocks_notification_when_strict_data_confirmation_diverges(monkeypatch):
    from super_trader_quant.backend.app.data_providers import factory

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scanner_engine, "STRATEGY_REGISTRY", {"AlwaysSignal": AlwaysSignalStrategy})
    monkeypatch.setattr(scanner_engine, "analyze_signal_quality", _strong_quality)
    monkeypatch.setattr(scanner_engine.settings, "signal_alert_min_level", "yellow")
    monkeypatch.setattr(scanner_engine.settings, "signal_data_confirmation_mode", "strict")
    monkeypatch.setattr(scanner_engine.settings, "signal_data_confirmation_provider", "brapi")
    monkeypatch.setattr(scanner_engine.settings, "signal_data_confirmation_markets", "BR")
    monkeypatch.setattr(scanner_engine.settings, "brapi_token", "token-123")
    monkeypatch.setattr(factory, "get_provider", lambda _name: DivergentConfirmationProvider())

    with Session(engine) as session:
        session.add(Asset(symbol="PETR4.SA", market="BR", country="Brasil"))
        session.commit()

        created = scanner_engine.scan_assets(session, PrimaryProvider(), symbols=["PETR4.SA"])
        signal = session.exec(select(Signal)).one()
        notifications = session.exec(select(Notification)).all()

    assert created
    assert signal.alert_level == "red"
    assert signal.data_source_status == "mismatch"
    assert signal.data_source_count == 2
    assert "quorum de dados" in signal.alert_reason
    assert notifications == []

