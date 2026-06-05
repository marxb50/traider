from .base import BaseStrategy
from .utils import apply_sided_levels


class InsideBarStrategy(BaseStrategy):
    name = "Inside_Bar"
    holding_period_bars = 6

    def prepare(self, df):
        inside = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
        long_signal = inside & (df["close"] >= df["open"])
        short_signal = inside & (df["close"] < df["open"])
        return apply_sided_levels(
            df,
            long_signal=long_signal,
            short_signal=short_signal,
            long_stop=df["low"],
            short_stop=df["high"],
        )
