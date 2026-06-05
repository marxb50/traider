from .base import BaseStrategy
from .utils import apply_sided_levels


class BullishEngulfingStrategy(BaseStrategy):
    name = "Engulfing"
    holding_period_bars = 6

    def prepare(self, df):
        previous_bearish = df["close"].shift(1) < df["open"].shift(1)
        current_bullish = df["close"] > df["open"]
        bullish_body_engulfed = (df["open"] <= df["close"].shift(1)) & (df["close"] >= df["open"].shift(1))
        previous_bullish = df["close"].shift(1) > df["open"].shift(1)
        current_bearish = df["close"] < df["open"]
        bearish_body_engulfed = (df["open"] >= df["close"].shift(1)) & (df["close"] <= df["open"].shift(1))
        return apply_sided_levels(
            df,
            long_signal=previous_bearish & current_bullish & bullish_body_engulfed,
            short_signal=previous_bullish & current_bearish & bearish_body_engulfed,
            long_stop=df["low"].rolling(2).min(),
            short_stop=df["high"].rolling(2).max(),
        )
