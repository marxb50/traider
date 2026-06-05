from .base import BaseStrategy
from .utils import apply_sided_levels


class VolumeBreakoutStrategy(BaseStrategy):
    name = "Volume_Breakout"
    holding_period_bars = 10

    def prepare(self, df):
        prior_high = df["high"].rolling(20).max().shift(1)
        prior_low = df["low"].rolling(20).min().shift(1)
        avg_volume = df["volume"].rolling(20).mean().shift(1)
        volume_expansion = df["volume"] > avg_volume * 1.5
        return apply_sided_levels(
            df,
            long_signal=(df["close"] > prior_high) & volume_expansion,
            short_signal=(df["close"] < prior_low) & volume_expansion,
            long_stop=df["low"].rolling(10).min().shift(1),
            short_stop=df["high"].rolling(10).max().shift(1),
        )
