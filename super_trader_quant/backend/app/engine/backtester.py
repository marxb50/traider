from __future__ import annotations
import pandas as pd
from .metrics import summarize_trades


def _trade_return_pct(side: str, entry_price: float, exit_price: float) -> float:
    if side == "short":
        return ((entry_price / exit_price) - 1) * 100
    return ((exit_price / entry_price) - 1) * 100


def run_backtest(df: pd.DataFrame, strategy) -> tuple[list[dict], dict]:
    prepared = strategy.prepare(df.copy()).reset_index(drop=True)
    trades: list[dict] = []
    i = 0
    while i < len(prepared) - 1:
        row = prepared.iloc[i]
        if not bool(row.get("signal", False)):
            i += 1
            continue
        entry_bar_index = i + 1
        entry_price = float(prepared.iloc[entry_bar_index]["open"])
        side = str(row.get("side", "long")).lower()
        stop = float(row["stop"])
        target = float(row["target"])
        exit_index = min(entry_bar_index + strategy.holding_period_bars - 1, len(prepared) - 1)
        exit_price = float(prepared.iloc[exit_index]["close"])
        outcome = "expired"
        for j in range(entry_bar_index, exit_index + 1):
            bar = prepared.iloc[j]
            # Regra conservadora: se stop e alvo forem tocados no mesmo candle, conta como stop.
            if side == "short":
                if float(bar["high"]) >= stop:
                    exit_index = j
                    exit_price = stop
                    outcome = "failure"
                    break
                if float(bar["low"]) <= target:
                    exit_index = j
                    exit_price = target
                    outcome = "success"
                    break
            else:
                if float(bar["low"]) <= stop:
                    exit_index = j
                    exit_price = stop
                    outcome = "failure"
                    break
                if float(bar["high"]) >= target:
                    exit_index = j
                    exit_price = target
                    outcome = "success"
                    break
        return_pct = _trade_return_pct(side, entry_price, exit_price)
        trades.append({
            "signal_time": prepared.iloc[i]["timestamp"],
            "entry_time": prepared.iloc[entry_bar_index]["timestamp"],
            "exit_time": prepared.iloc[exit_index]["timestamp"],
            "bars_held": exit_index - entry_bar_index + 1,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "stop": stop,
            "target": target,
            "outcome": outcome,
            "return_pct": return_pct,
        })
        i = exit_index + 1
    return trades, summarize_trades(trades)
