from .base import BaseStrategy
from .utils import apply_sided_levels


class PFRStrategy(BaseStrategy):
    name = "PFR"
    holding_period_bars = 6

    def prepare(self, df):
        long_signal = (df["low"] < df["low"].shift(1)) & (df["close"] > df["close"].shift(1))
        short_signal = (df["high"] > df["high"].shift(1)) & (df["close"] < df["close"].shift(1))
        return apply_sided_levels(
            df,
            long_signal=long_signal,
            short_signal=short_signal,
            long_stop=df["low"],
            short_stop=df["high"],
        )
