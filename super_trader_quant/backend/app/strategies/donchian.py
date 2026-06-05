from .base import BaseStrategy
from .utils import apply_sided_levels


class DonchianStrategy(BaseStrategy):
    name = "Donchian"
    holding_period_bars = 20

    def prepare(self, df):
        upper_breakout = df["high"].rolling(20).max().shift(1)
        lower_breakdown = df["low"].rolling(20).min().shift(1)
        return apply_sided_levels(
            df,
            long_signal=df["close"] > upper_breakout,
            short_signal=df["close"] < lower_breakdown,
            long_stop=df["low"].rolling(10).min().shift(1),
            short_stop=df["high"].rolling(10).max().shift(1),
        )
