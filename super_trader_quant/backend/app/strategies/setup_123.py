from .base import BaseStrategy
from .utils import apply_sided_levels


class Setup123Strategy(BaseStrategy):
    name = "Setup_123"
    holding_period_bars = 8

    def prepare(self, df):
        middle_is_low = (df["low"].shift(1) < df["low"].shift(2)) & (df["low"].shift(1) < df["low"])
        middle_is_high = (df["high"].shift(1) > df["high"].shift(2)) & (df["high"].shift(1) > df["high"])
        return apply_sided_levels(
            df,
            long_signal=middle_is_low,
            short_signal=middle_is_high,
            long_stop=df["low"].shift(1),
            short_stop=df["high"].shift(1),
        )
