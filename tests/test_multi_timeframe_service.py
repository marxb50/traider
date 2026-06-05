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


class AlwaysShortSignalStrategy(BaseStrategy):
    name = "AlwaysShortSignal"
    holding_period_bars = 3

    def prepare(self, df):
        prepared = df.copy()
        prepared["signal"] = False
        prepared.loc[prepared.index[-1], "signal"] = True
        prepared["side"] = "short"
        prepared["stop"] = prepared["close"] * 1.02
        prepared["target"] = prepared["close"] * 0.96
        return prepared


class MultiTimeframeProvider:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def fetch_many_history(self, symbols, timeframe="D1", period="1y"):
        self.calls.append((timeframe, period))
        if timeframe == "H1":
            frame = _frame(rows=60, freq="h", direction=1)
        else:
            frame = _frame(rows=60, freq="D", direction=-1)
        return {symbol: frame.copy() for symbol in symbols}


def _frame(rows: int, freq: str, direction: int):
    start = datetime(2026, 1, 1)
    values = [100 + direction * i for i in range(rows)]
    return pd.DataFrame(
        [
            {
                "timestamp": start + (timedelta(hours=i) if freq == "h" else timedelta(days=i)),
                "open": value,
                "high": value + 1,
                "low": value - 1,
                "close": value,
                "volume": 1,
            }
            for i, value in enumerate(values)
        ]
    )


def test_h1_scanner_uses_weekly_daily_context_and_blocks_bearish_mtf(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    provider = MultiTimeframeProvider()
    monkeypatch.setattr(scanner_engine, "STRATEGY_REGISTRY", {"AlwaysSignal": AlwaysSignalStrategy})
    monkeypatch.setattr(scanner_engine.settings, "signal_alert_min_level", "yellow")
    monkeypatch.setattr(scanner_engine.settings, "scan_intraday_period", "3mo")
    monkeypatch.setattr(scanner_engine.settings, "scan_daily_period", "1y")
    monkeypatch.setattr(scanner_engine.settings, "scan_weekly_period", "2y")

    def strong_quality(_df, _strategy, _payload):
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

    monkeypatch.setattr(scanner_engine, "analyze_signal_quality", strong_quality)

    with Session(engine) as session:
        session.add(Asset(symbol="TEST3.SA", market="BR", country="Brasil"))
        session.commit()

        created = scanner_engine.scan_assets(session, provider, timeframe="H1", symbols=["TEST3.SA"])
        signal = session.exec(select(Signal)).one()
        notifications = session.exec(select(Notification)).all()

    assert created
    assert provider.calls == [("H1", "3mo"), ("W1", "2y"), ("D1", "1y")]
    assert signal.alert_level == "red"
    assert "contexto MTF" in signal.alert_reason
    assert "bloqueado" in signal.alert_reason
    assert notifications == []


def test_h1_scanner_allows_short_signal_with_bearish_mtf(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    provider = MultiTimeframeProvider()
    monkeypatch.setattr(scanner_engine, "STRATEGY_REGISTRY", {"AlwaysShortSignal": AlwaysShortSignalStrategy})
    monkeypatch.setattr(scanner_engine.settings, "signal_alert_min_level", "yellow")
    monkeypatch.setattr(scanner_engine.settings, "scan_intraday_period", "3mo")
    monkeypatch.setattr(scanner_engine.settings, "scan_daily_period", "1y")
    monkeypatch.setattr(scanner_engine.settings, "scan_weekly_period", "2y")
    monkeypatch.setattr(scanner_engine.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(scanner_engine.settings, "telegram_chat_ids", "111111111")

    def strong_quality(_df, _strategy, _payload):
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
            target_pct=-4.0,
            stop_pct=2.0,
            reason="historico forte",
        )

    monkeypatch.setattr(scanner_engine, "analyze_signal_quality", strong_quality)

    with Session(engine) as session:
        session.add(Asset(symbol="TEST3.SA", market="BR", country="Brasil"))
        session.commit()

        created = scanner_engine.scan_assets(session, provider, timeframe="H1", symbols=["TEST3.SA"])
        signal = session.exec(select(Signal)).one()
        notifications = session.exec(select(Notification)).all()

    assert created
    assert signal.side == "short"
    assert signal.alert_level == "green"
    assert "alinhado para venda" in signal.alert_reason
    assert notifications
    assert all(notification.kind == "signal_opened" for notification in notifications)
