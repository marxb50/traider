from .base import BaseStrategy
from .utils import apply_sided_levels


class MACDCrossStrategy(BaseStrategy):
    name = "MACD_Cross"
    holding_period_bars = 8

    def prepare(self, df):
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        ema50 = df["close"].ewm(span=50, adjust=False).mean()
        crossed_up = (macd > signal_line) & (macd.shift(1) <= signal_line.shift(1))
        crossed_down = (macd < signal_line) & (macd.shift(1) >= signal_line.shift(1))
        return apply_sided_levels(
            df,
            long_signal=crossed_up & (df["close"] > ema50),
            short_signal=crossed_down & (df["close"] < ema50),
            long_stop=df["low"].rolling(5).min(),
            short_stop=df["high"].rolling(5).max(),
        )
