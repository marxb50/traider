import numpy as np
import pandas as pd


def equity_curve_from_returns(returns: list[float]) -> pd.Series:
    if not returns:
        return pd.Series(dtype="float64")
    return (1 + pd.Series(returns)).cumprod()


def max_drawdown(returns: list[float]) -> float:
    curve = equity_curve_from_returns(returns)
    if curve.empty:
        return 0.0
    peaks = curve.cummax()
    drawdowns = curve / peaks - 1
    return float(drawdowns.min())


def summarize_trades(trades: list[dict]) -> dict:
    returns = [trade["return_pct"] / 100 for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(trades),
        "total_return_pct": float(round(((1 + pd.Series(returns)).prod() - 1) * 100, 4)) if returns else 0.0,
        "win_rate": round((len(wins) / len(returns)) * 100, 4) if returns else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else float("inf") if gross_profit else 0.0,
        "max_drawdown_pct": round(max_drawdown(returns) * 100, 4),
        "ev_pct": round(float(np.mean(returns) * 100), 4) if returns else 0.0,
    }
