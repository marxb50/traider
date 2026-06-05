from .base import BaseStrategy
from .utils import apply_sided_levels


class BollingerStrategy(BaseStrategy):
    name = "Bollinger"
    holding_period_bars = 6

    def prepare(self, df):
        ma = df["close"].rolling(20).mean()
        std = df["close"].rolling(20).std()
        lower = ma - 2 * std
        upper = ma + 2 * std
        long_signal = (df["close"].shift(1) < lower.shift(1)) & (df["close"] > lower)
        short_signal = (df["close"].shift(1) > upper.shift(1)) & (df["close"] < upper)
        return apply_sided_levels(
            df,
            long_signal=long_signal,
            short_signal=short_signal,
            long_stop=df["low"].rolling(3).min(),
            short_stop=df["high"].rolling(3).max(),
        )
