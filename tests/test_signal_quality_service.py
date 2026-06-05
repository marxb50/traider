from datetime import datetime, timedelta

import pandas as pd

from super_trader_quant.backend.app.services import signal_quality_service


class RepeatSuccessStrategy:
    name = "RepeatSuccess"
    holding_period_bars = 1

    def prepare(self, df):
        prepared = df.copy()
        prepared["signal"] = False
        prepared.loc[prepared.index % 2 == 0, "signal"] = True
        prepared["stop"] = 98.0
        prepared["target"] = 104.0
        return prepared


def _frame(rows: int = 25):
    start = datetime(2026, 1, 1)
    return pd.DataFrame(
        [
            {
                "timestamp": start + timedelta(days=index),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1.0,
            }
            for index in range(rows)
        ]
    )


def test_signal_quality_grades_strong_history_green(monkeypatch):
    monkeypatch.setattr(signal_quality_service.settings, "signal_alert_green_min_sample_size", 10)
    monkeypatch.setattr(signal_quality_service.settings, "signal_alert_green_min_probability", 0.58)

    payload = {
        "signal_time": _frame().iloc[-1]["timestamp"],
        "entry": 100.0,
        "stop": 98.0,
        "target": 104.0,
    }

    quality = signal_quality_service.analyze_signal_quality(_frame(), RepeatSuccessStrategy(), payload)

    assert quality.level == "green"
    assert quality.probability_pct >= 70
    assert quality.sample_size >= 10
    assert quality.avg_bars_to_target == 1.0


def test_signal_quality_suppresses_weak_sample_as_red():
    df = _frame(rows=2)
    payload = {
        "signal_time": df.iloc[-1]["timestamp"],
        "entry": 100.0,
        "stop": 98.0,
        "target": 102.0,
    }

    quality = signal_quality_service.analyze_signal_quality(df, RepeatSuccessStrategy(), payload)

    assert quality.level == "red"
    assert signal_quality_service.is_alert_level_enabled(quality.level) is False


def test_signal_quality_calculates_short_risk_reward_and_message():
    df = _frame(rows=2)
    payload = {
        "signal_time": df.iloc[-1]["timestamp"],
        "side": "short",
        "entry": 100.0,
        "stop": 102.0,
        "target": 96.0,
    }

    quality = signal_quality_service.analyze_signal_quality(df, RepeatSuccessStrategy(), payload)
    signal = type(
        "SignalStub",
        (),
        {
            "strategy": "Donchian",
            "asset_symbol": "VALE3.SA",
            "timeframe": "D1",
            "holding_period_bars": 5,
            "side": "short",
            "entry": 100.0,
            "stop": 102.0,
            "target": 96.0,
        },
    )()

    message = signal_quality_service.format_signal_opened_message(signal, quality)

    assert quality.risk_reward == 2.0
    assert quality.stop_pct == 2.0
    assert quality.target_pct == -4.0
    assert "ALERTA VERMELHO VENDA" in message
    assert "chance de acerto historica estimada:" in message
    assert "stop: 102.00 (+2.00%) | alvo: 96.00 (-4.00%)" in message


def test_unclassified_alert_level_is_not_enabled():
    assert signal_quality_service.is_alert_level_enabled(None) is False


def test_resolved_signal_message_shows_hit_probability():
    signal = type(
        "SignalStub",
        (),
        {
            "strategy": "PFR",
            "asset_symbol": "PETR4.SA",
            "timeframe": "H1",
            "status": "success",
            "side": "long",
            "alert_level": "yellow",
            "alert_probability_pct": 62.5,
            "alert_avg_bars_to_target": 4.0,
            "pnl_pct": 2.4,
        },
    )()

    message = signal_quality_service.format_signal_resolved_message(signal)

    assert "chance de acerto historica: 62.5%" in message


def test_signal_message_explains_daily_candle_timeframe():
    quality = signal_quality_service.SignalQuality(
        level="yellow",
        score=61.0,
        probability_pct=55.0,
        sample_size=12,
        successes=7,
        failures=3,
        expired=2,
        avg_pnl_pct=0.4,
        avg_bars_to_target=3.0,
        risk_reward=1.5,
        target_pct=4.0,
        stop_pct=-2.0,
        reason="historico aceitavel",
    )
    signal = type(
        "SignalStub",
        (),
        {
            "strategy": "PFR",
            "asset_symbol": "PETR4.SA",
            "timeframe": "D1",
            "holding_period_bars": 5,
            "entry": 100.0,
            "stop": 98.0,
            "target": 104.0,
        },
    )()

    message = signal_quality_service.format_signal_opened_message(signal, quality)

    assert "timeframe: D1 diario: 1 candle = 1 pregao/dia util" in message
    assert "3.0 candles D1 (~3.0 pregoes/dias uteis)" in message
    assert "5.0 candles D1 (~5.0 pregoes/dias uteis)" in message


def test_signal_message_explains_hourly_candle_timeframe():
    quality = signal_quality_service.SignalQuality(
        level="yellow",
        score=61.0,
        probability_pct=55.0,
        sample_size=12,
        successes=7,
        failures=3,
        expired=2,
        avg_pnl_pct=0.4,
        avg_bars_to_target=4.0,
        risk_reward=1.5,
        target_pct=4.0,
        stop_pct=-2.0,
        reason="historico aceitavel",
    )
    signal = type(
        "SignalStub",
        (),
        {
            "strategy": "PFR",
            "asset_symbol": "PETR4.SA",
            "timeframe": "H1",
            "holding_period_bars": 6,
            "entry": 100.0,
            "stop": 98.0,
            "target": 104.0,
        },
    )()

    message = signal_quality_service.format_signal_opened_message(signal, quality)

    assert "timeframe: H1/60 minutos: 1 candle = 1 hora de negociacao" in message
    assert "4.0 candles H1 (~4.0 horas de negociacao)" in message
    assert "6.0 candles H1 (~6.0 horas de negociacao)" in message
