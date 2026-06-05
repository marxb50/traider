import pandas as pd
from super_trader_quant.backend.app.engine.backtester import run_backtest
from super_trader_quant.backend.app.strategies.base import BaseStrategy


class OneShotStrategy(BaseStrategy):
    name = "OneShot"
    holding_period_bars = 2

    def prepare(self, df):
        df["signal"] = False
        df.loc[0, "signal"] = True
        df["stop"] = 95
        df["target"] = 110
        return df


class ShortShotStrategy(BaseStrategy):
    name = "ShortShot"
    holding_period_bars = 2

    def prepare(self, df):
        df["signal"] = False
        df.loc[0, "signal"] = True
        df["side"] = "short"
        df["stop"] = 105
        df["target"] = 90
        return df


def test_backtester_enters_on_next_candle():
    df = pd.DataFrame([
        {"timestamp": "2026-01-01", "open": 100, "high": 101, "low": 99, "close": 100},
        {"timestamp": "2026-01-02", "open": 102, "high": 111, "low": 101, "close": 108},
        {"timestamp": "2026-01-03", "open": 108, "high": 109, "low": 107, "close": 108},
    ])
    trades, metrics = run_backtest(df, OneShotStrategy())
    assert len(trades) == 1
    assert trades[0]["entry_price"] == 102
    assert trades[0]["outcome"] == "success"
    assert metrics["trades"] == 1


def test_backtester_supports_short_signal_target():
    df = pd.DataFrame([
        {"timestamp": "2026-01-01", "open": 100, "high": 101, "low": 99, "close": 100},
        {"timestamp": "2026-01-02", "open": 100, "high": 102, "low": 89, "close": 92},
        {"timestamp": "2026-01-03", "open": 92, "high": 93, "low": 88, "close": 90},
    ])

    trades, metrics = run_backtest(df, ShortShotStrategy())

    assert len(trades) == 1
    assert trades[0]["side"] == "short"
    assert trades[0]["entry_price"] == 100
    assert trades[0]["exit_price"] == 90
    assert trades[0]["outcome"] == "success"
    assert round(trades[0]["return_pct"], 3) == 11.111
    assert metrics["trades"] == 1
