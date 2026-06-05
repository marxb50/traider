from .base import BaseStrategy
from .utils import apply_sided_levels


class TrapNaMediaStrategy(BaseStrategy):
    name = "Trap_na_Media"
    holding_period_bars = 6

    def prepare(self, df):
        ma = df["close"].rolling(20).mean()
        above_before = (df["close"].shift(3) > ma.shift(3)) & (df["close"].shift(2) > ma.shift(2))
        pierced = df["low"].shift(1) < ma.shift(1)
        recovered = df["close"] > df["high"].shift(1)
        below_before = (df["close"].shift(3) < ma.shift(3)) & (df["close"].shift(2) < ma.shift(2))
        pierced_up = df["high"].shift(1) > ma.shift(1)
        rejected = df["close"] < df["low"].shift(1)
        return apply_sided_levels(
            df,
            long_signal=above_before & pierced & recovered,
            short_signal=below_before & pierced_up & rejected,
            long_stop=df["low"].shift(1),
            short_stop=df["high"].shift(1),
        )
