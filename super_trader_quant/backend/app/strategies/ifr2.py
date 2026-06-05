from .base import BaseStrategy
from .utils import apply_sided_levels, rsi


class IFR2Strategy(BaseStrategy):
    name = "IFR2"
    holding_period_bars = 5

    def prepare(self, df):
        df["ifr2"] = rsi(df["close"], 2)
        long_signal = df["ifr2"] < 10
        short_signal = df["ifr2"] > 90
        return apply_sided_levels(
            df,
            long_signal=long_signal,
            short_signal=short_signal,
            long_stop=df["low"].rolling(3).min(),
            short_stop=df["high"].rolling(3).max(),
        )
