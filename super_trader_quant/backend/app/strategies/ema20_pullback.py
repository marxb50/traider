from .base import BaseStrategy
from .utils import apply_sided_levels


class EMA20PullbackStrategy(BaseStrategy):
    name = "EMA20_Pullback"
    holding_period_bars = 6

    def prepare(self, df):
        ema20 = df["close"].ewm(span=20, adjust=False).mean()
        ema50 = df["close"].ewm(span=50, adjust=False).mean()
        trend_ok = (df["close"] > ema50) & (ema20 > ema50)
        touched_ema = df["low"] <= ema20
        recovered = (df["close"] > ema20) & (df["close"] > df["high"].shift(1))
        downtrend_ok = (df["close"] < ema50) & (ema20 < ema50)
        touched_from_below = df["high"] >= ema20
        rejected = (df["close"] < ema20) & (df["close"] < df["low"].shift(1))
        return apply_sided_levels(
            df,
            long_signal=trend_ok & touched_ema & recovered,
            short_signal=downtrend_ok & touched_from_below & rejected,
            long_stop=df["low"].rolling(3).min(),
            short_stop=df["high"].rolling(3).max(),
        )
