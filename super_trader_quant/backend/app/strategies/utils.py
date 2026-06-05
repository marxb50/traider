import numpy as np
import pandas as pd


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def apply_sided_levels(
    df: pd.DataFrame,
    long_signal: pd.Series,
    short_signal: pd.Series,
    long_stop: pd.Series,
    short_stop: pd.Series,
    reward_multiple: float = 2.0,
) -> pd.DataFrame:
    long_signal = long_signal.fillna(False).astype(bool)
    short_signal = short_signal.fillna(False).astype(bool) & ~long_signal

    long_risk = (df["close"] - long_stop).clip(lower=df["close"] * 0.01)
    short_risk = (short_stop - df["close"]).clip(lower=df["close"] * 0.01)

    df["side"] = "long"
    df["stop"] = long_stop
    df["target"] = df["close"] + reward_multiple * long_risk
    df.loc[short_signal, "side"] = "short"
    df.loc[short_signal, "stop"] = short_stop[short_signal]
    df.loc[short_signal, "target"] = df["close"][short_signal] - reward_multiple * short_risk[short_signal]
    valid_long = (df["side"] == "long") & (df["stop"] < df["close"]) & (df["target"] > df["close"])
    valid_short = (df["side"] == "short") & (df["stop"] > df["close"]) & (df["target"] < df["close"])
    df["signal"] = (long_signal | short_signal) & df["stop"].notna() & df["target"].notna() & (valid_long | valid_short)
    return df
