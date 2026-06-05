import pandas as pd
from .base import BaseStrategy
from .utils import apply_sided_levels, atr


class SupertrendStrategy(BaseStrategy):
    name = "Supertrend"
    holding_period_bars = 10

    def prepare(self, df):
        hl2 = (df["high"] + df["low"]) / 2
        atr_value = atr(df, 10)
        upper = hl2 + 3 * atr_value
        lower = hl2 - 3 * atr_value
        trend = pd.Series(index=df.index, dtype="float64")
        trend.iloc[0] = 1
        for i in range(1, len(df)):
            prev_trend = trend.iloc[i - 1]
            if df["close"].iloc[i] > upper.iloc[i - 1]:
                trend.iloc[i] = 1
            elif df["close"].iloc[i] < lower.iloc[i - 1]:
                trend.iloc[i] = -1
            else:
                trend.iloc[i] = prev_trend
                if trend.iloc[i] == 1 and lower.iloc[i] < lower.iloc[i - 1]:
                    lower.iloc[i] = lower.iloc[i - 1]
                if trend.iloc[i] == -1 and upper.iloc[i] > upper.iloc[i - 1]:
                    upper.iloc[i] = upper.iloc[i - 1]
        return apply_sided_levels(
            df,
            long_signal=(trend == 1) & (trend.shift(1) == -1),
            short_signal=(trend == -1) & (trend.shift(1) == 1),
            long_stop=lower,
            short_stop=upper,
        )
