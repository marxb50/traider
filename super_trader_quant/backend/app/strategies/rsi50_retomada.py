from .base import BaseStrategy
from .utils import apply_sided_levels, rsi


class RSI50RetomadaStrategy(BaseStrategy):
    name = "RSI50_Retomada"
    holding_period_bars = 6

    def prepare(self, df):
        rsi14 = rsi(df["close"], 14)
        ema20 = df["close"].ewm(span=20, adjust=False).mean()
        ema50 = df["close"].ewm(span=50, adjust=False).mean()
        crossed_strength = (rsi14 > 50) & (rsi14.shift(1) <= 50)
        trend_ok = (df["close"] > ema20) & (ema20 > ema50)
        crossed_weakness = (rsi14 < 50) & (rsi14.shift(1) >= 50)
        downtrend_ok = (df["close"] < ema20) & (ema20 < ema50)
        return apply_sided_levels(
            df,
            long_signal=crossed_strength & trend_ok,
            short_signal=crossed_weakness & downtrend_ok,
            long_stop=df["low"].rolling(5).min(),
            short_stop=df["high"].rolling(5).max(),
        )
