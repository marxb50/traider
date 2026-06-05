import json
import sys

import pandas as pd

from scripts import run_backtest_batch


class _FakeProvider:
    def fetch_history(self, symbol: str, timeframe: str = "D1", period: str = "1y") -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"timestamp": "2026-01-01", "open": 100, "high": 101, "low": 99, "close": 100},
                {"timestamp": "2026-01-02", "open": 101, "high": 110, "low": 100, "close": 109},
                {"timestamp": "2026-01-03", "open": 109, "high": 111, "low": 108, "close": 110},
            ]
        )


class _FakeStrategy:
    name = "fake_strategy"
    holding_period_bars = 2

    def prepare(self, df):
        frame = df.copy()
        frame["signal"] = False
        frame.loc[0, "signal"] = True
        frame["stop"] = 95
        frame["target"] = 108
        return frame


def test_run_backtest_batch_processes_more_than_five_assets_and_writes_output(tmp_path, monkeypatch):
    output_path = tmp_path / "batch.json"
    monkeypatch.setattr(run_backtest_batch, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        run_backtest_batch,
        "DEMO_ASSETS_BY_MARKET",
        {"BR": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]},
    )
    monkeypatch.setattr(run_backtest_batch, "STRATEGY_REGISTRY", {"fake_strategy": _FakeStrategy})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_backtest_batch",
            "--provider",
            "fake",
            "--market",
            "BR",
            "--limit",
            "6",
            "--output",
            str(output_path),
        ],
    )

    run_backtest_batch.main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload) == 6
    assert {row["symbol"] for row in payload} == {"AAA", "BBB", "CCC", "DDD", "EEE", "FFF"}
    assert all(row["ok"] is True for row in payload)
