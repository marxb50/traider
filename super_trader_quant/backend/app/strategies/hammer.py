from .base import BaseStrategy
from .utils import apply_sided_levels


class HammerStrategy(BaseStrategy):
    name = "Hammer_Star"
    holding_period_bars = 6

    def prepare(self, df):
        candle_range = (df["high"] - df["low"]).replace(0, 0.01)
        body = (df["close"] - df["open"]).abs()
        upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
        lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
        ema20 = df["close"].ewm(span=20, adjust=False).mean()
        hammer_shape = (body <= candle_range * 0.35) & (lower_wick >= body * 2) & (upper_wick <= candle_range * 0.3)
        shooting_star_shape = (
            (body <= candle_range * 0.35)
            & (upper_wick >= body * 2)
            & (lower_wick <= candle_range * 0.3)
        )
        return apply_sided_levels(
            df,
            long_signal=hammer_shape & (df["close"] > df["open"]) & (df["low"] <= ema20),
            short_signal=shooting_star_shape & (df["close"] < df["open"]) & (df["high"] >= ema20),
            long_stop=df["low"],
            short_stop=df["high"],
        )
