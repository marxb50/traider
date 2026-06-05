from .base import BaseStrategy
from .utils import apply_sided_levels


class EMACrossStrategy(BaseStrategy):
    name = "EMA_Cross"
    holding_period_bars = 8

    def prepare(self, df):
        ema9 = df["close"].ewm(span=9, adjust=False).mean()
        ema21 = df["close"].ewm(span=21, adjust=False).mean()
        ema50 = df["close"].ewm(span=50, adjust=False).mean()
        crossed_up = (ema9 > ema21) & (ema9.shift(1) <= ema21.shift(1))
        crossed_down = (ema9 < ema21) & (ema9.shift(1) >= ema21.shift(1))
        return apply_sided_levels(
            df,
            long_signal=crossed_up & (df["close"] > ema50),
            short_signal=crossed_down & (df["close"] < ema50),
            long_stop=df["low"].rolling(5).min(),
            short_stop=df["high"].rolling(5).max(),
        )
