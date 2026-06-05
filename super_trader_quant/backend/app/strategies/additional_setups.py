from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseStrategy
from .utils import apply_sided_levels, atr, rsi


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3


def _rolling_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    volume = df["volume"].replace(0, np.nan)
    return (_typical_price(df) * volume).rolling(period).sum() / volume.rolling(period).sum()


def _cross_above(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left > right) & (left.shift(1) <= right.shift(1))


def _cross_below(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left < right) & (left.shift(1) >= right.shift(1))


def _default_long_stop(df: pd.DataFrame, period: int = 10) -> pd.Series:
    return df["low"].rolling(period).min()


def _default_short_stop(df: pd.DataFrame, period: int = 10) -> pd.Series:
    return df["high"].rolling(period).max()


def _obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def _money_flow_index(df: pd.DataFrame, period: int = 14) -> pd.Series:
    typical = _typical_price(df)
    flow = typical * df["volume"]
    positive = flow.where(typical > typical.shift(1), 0.0)
    negative = flow.where(typical < typical.shift(1), 0.0)
    ratio = positive.rolling(period).sum() / negative.rolling(period).sum().replace(0, np.nan)
    return 100 - (100 / (1 + ratio))


def _cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    typical = _typical_price(df)
    average = typical.rolling(period).mean()
    mean_dev = (typical - average).abs().rolling(period).mean()
    return (typical - average) / (0.015 * mean_dev.replace(0, np.nan))


def _stochastic_k(df: pd.DataFrame, period: int = 14) -> pd.Series:
    lowest = df["low"].rolling(period).min()
    highest = df["high"].rolling(period).max()
    return 100 * (df["close"] - lowest) / (highest - lowest).replace(0, np.nan)


def _williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    lowest = df["low"].rolling(period).min()
    highest = df["high"].rolling(period).max()
    return -100 * (highest - df["close"]) / (highest - lowest).replace(0, np.nan)


def _adx_components(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    smoothed_tr = true_range.ewm(alpha=1 / period, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / smoothed_tr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / smoothed_tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


class SMA2050CrossStrategy(BaseStrategy):
    name = "SMA20_50_Cross"
    holding_period_bars = 12

    def prepare(self, df):
        fast = df["close"].rolling(20).mean()
        slow = df["close"].rolling(50).mean()
        return apply_sided_levels(df, _cross_above(fast, slow), _cross_below(fast, slow), _default_long_stop(df), _default_short_stop(df))


class EMA921CrossStrategy(BaseStrategy):
    name = "EMA9_21_Cross"
    holding_period_bars = 8

    def prepare(self, df):
        fast = _ema(df["close"], 9)
        slow = _ema(df["close"], 21)
        return apply_sided_levels(df, _cross_above(fast, slow), _cross_below(fast, slow), _default_long_stop(df, 8), _default_short_stop(df, 8))


class VWAPReclaimStrategy(BaseStrategy):
    name = "VWAP_Reclaim"
    holding_period_bars = 6

    def prepare(self, df):
        vwap = _rolling_vwap(df, 20)
        return apply_sided_levels(df, _cross_above(df["close"], vwap), _cross_below(df["close"], vwap), df["low"].rolling(5).min(), df["high"].rolling(5).max())


class VWAPPullbackStrategy(BaseStrategy):
    name = "VWAP_Pullback"
    holding_period_bars = 6

    def prepare(self, df):
        vwap = _rolling_vwap(df, 20)
        long_signal = (df["close"] > vwap) & (df["low"] <= vwap) & (df["close"] > df["open"])
        short_signal = (df["close"] < vwap) & (df["high"] >= vwap) & (df["close"] < df["open"])
        return apply_sided_levels(df, long_signal, short_signal, df["low"].rolling(5).min(), df["high"].rolling(5).max())


class NR7BreakoutStrategy(BaseStrategy):
    name = "NR7_Breakout"
    holding_period_bars = 8

    def prepare(self, df):
        candle_range = df["high"] - df["low"]
        nr7_previous = candle_range.shift(1) <= candle_range.rolling(7).min().shift(1)
        long_signal = nr7_previous & (df["close"] > df["high"].shift(1))
        short_signal = nr7_previous & (df["close"] < df["low"].shift(1))
        return apply_sided_levels(df, long_signal, short_signal, df["low"].shift(1), df["high"].shift(1))


class SqueezeBreakoutStrategy(BaseStrategy):
    name = "Squeeze_Breakout"
    holding_period_bars = 10

    def prepare(self, df):
        mid = df["close"].rolling(20).mean()
        std = df["close"].rolling(20).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        width = (upper - lower) / mid.replace(0, np.nan)
        squeezed = width.shift(1) <= width.rolling(40).quantile(0.2).shift(1)
        long_signal = squeezed & (df["close"] > upper)
        short_signal = squeezed & (df["close"] < lower)
        return apply_sided_levels(df, long_signal, short_signal, _default_long_stop(df), _default_short_stop(df))


class KeltnerBreakoutStrategy(BaseStrategy):
    name = "Keltner_Breakout"
    holding_period_bars = 10

    def prepare(self, df):
        center = _ema(df["close"], 20)
        range_atr = atr(df, 14)
        upper = center + 1.5 * range_atr
        lower = center - 1.5 * range_atr
        return apply_sided_levels(df, _cross_above(df["close"], upper), _cross_below(df["close"], lower), center - range_atr, center + range_atr)


class ADXTrendPullbackStrategy(BaseStrategy):
    name = "ADX_Trend_Pullback"
    holding_period_bars = 10

    def prepare(self, df):
        adx, plus_di, minus_di = _adx_components(df, 14)
        ema20 = _ema(df["close"], 20)
        ema50 = _ema(df["close"], 50)
        rsi14 = rsi(df["close"], 14)
        long_signal = (adx > 20) & (plus_di > minus_di) & (df["close"] > ema50) & (df["low"] <= ema20) & (df["close"] > ema20) & (rsi14.between(40, 62))
        short_signal = (adx > 20) & (minus_di > plus_di) & (df["close"] < ema50) & (df["high"] >= ema20) & (df["close"] < ema20) & (rsi14.between(38, 60))
        return apply_sided_levels(df, long_signal, short_signal, df["low"].rolling(8).min(), df["high"].rolling(8).max())


class CCIReversalStrategy(BaseStrategy):
    name = "CCI_Reversal"
    holding_period_bars = 7

    def prepare(self, df):
        cci = _cci(df, 20)
        return apply_sided_levels(df, _cross_above(cci, pd.Series(-100, index=df.index)), _cross_below(cci, pd.Series(100, index=df.index)), _default_long_stop(df, 6), _default_short_stop(df, 6))


class StochasticCrossStrategy(BaseStrategy):
    name = "Stochastic_Cross"
    holding_period_bars = 7

    def prepare(self, df):
        k = _stochastic_k(df, 14)
        d = k.rolling(3).mean()
        long_signal = _cross_above(k, d) & (k < 30)
        short_signal = _cross_below(k, d) & (k > 70)
        return apply_sided_levels(df, long_signal, short_signal, _default_long_stop(df, 6), _default_short_stop(df, 6))


class WilliamsRReversalStrategy(BaseStrategy):
    name = "WilliamsR_Reversal"
    holding_period_bars = 7

    def prepare(self, df):
        wr = _williams_r(df, 14)
        return apply_sided_levels(df, _cross_above(wr, pd.Series(-80, index=df.index)), _cross_below(wr, pd.Series(-20, index=df.index)), _default_long_stop(df, 6), _default_short_stop(df, 6))


class ROCMomentumStrategy(BaseStrategy):
    name = "ROC_Momentum"
    holding_period_bars = 8

    def prepare(self, df):
        roc = df["close"].pct_change(12) * 100
        volume_ok = df["volume"] > df["volume"].rolling(20).mean()
        return apply_sided_levels(df, _cross_above(roc, pd.Series(0, index=df.index)) & volume_ok, _cross_below(roc, pd.Series(0, index=df.index)) & volume_ok, _default_long_stop(df, 8), _default_short_stop(df, 8))


class OBVBreakoutStrategy(BaseStrategy):
    name = "OBV_Breakout"
    holding_period_bars = 10

    def prepare(self, df):
        obv = _obv(df)
        ema20 = _ema(df["close"], 20)
        long_signal = (obv > obv.rolling(20).max().shift(1)) & (df["close"] > ema20)
        short_signal = (obv < obv.rolling(20).min().shift(1)) & (df["close"] < ema20)
        return apply_sided_levels(df, long_signal, short_signal, _default_long_stop(df, 10), _default_short_stop(df, 10))


class MFIReversalStrategy(BaseStrategy):
    name = "MFI_Reversal"
    holding_period_bars = 7

    def prepare(self, df):
        mfi = _money_flow_index(df, 14)
        return apply_sided_levels(df, _cross_above(mfi, pd.Series(20, index=df.index)), _cross_below(mfi, pd.Series(80, index=df.index)), _default_long_stop(df, 6), _default_short_stop(df, 6))


class GapContinuationStrategy(BaseStrategy):
    name = "Gap_Continuation"
    holding_period_bars = 5

    def prepare(self, df):
        prev_high = df["high"].shift(1)
        prev_low = df["low"].shift(1)
        long_signal = (df["open"] > prev_high * 1.003) & (df["close"] > df["open"])
        short_signal = (df["open"] < prev_low * 0.997) & (df["close"] < df["open"])
        return apply_sided_levels(df, long_signal, short_signal, df["low"], df["high"])


class GapFadeStrategy(BaseStrategy):
    name = "Gap_Fade"
    holding_period_bars = 5

    def prepare(self, df):
        prev_high = df["high"].shift(1)
        prev_low = df["low"].shift(1)
        long_signal = (df["open"] < prev_low * 0.997) & (df["close"] > prev_low)
        short_signal = (df["open"] > prev_high * 1.003) & (df["close"] < prev_high)
        return apply_sided_levels(df, long_signal, short_signal, df["low"], df["high"])


class ThreeBarReversalStrategy(BaseStrategy):
    name = "Three_Bar_Reversal"
    holding_period_bars = 6

    def prepare(self, df):
        lower_sequence = (df["low"].shift(2) > df["low"].shift(1)) & (df["low"].shift(1) > df["low"])
        higher_sequence = (df["high"].shift(2) < df["high"].shift(1)) & (df["high"].shift(1) < df["high"])
        long_signal = lower_sequence.shift(1, fill_value=False) & (df["close"] > df["high"].shift(1))
        short_signal = higher_sequence.shift(1, fill_value=False) & (df["close"] < df["low"].shift(1))
        return apply_sided_levels(df, long_signal, short_signal, df["low"].rolling(4).min(), df["high"].rolling(4).max())


class PinBarReversalStrategy(BaseStrategy):
    name = "Pin_Bar_Reversal"
    holding_period_bars = 5

    def prepare(self, df):
        body = (df["close"] - df["open"]).abs().replace(0, np.nan)
        upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
        lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
        long_signal = (lower_wick > 2.5 * body) & (upper_wick < body) & (df["close"] > df["open"])
        short_signal = (upper_wick > 2.5 * body) & (lower_wick < body) & (df["close"] < df["open"])
        return apply_sided_levels(df, long_signal, short_signal, df["low"], df["high"])


class MarubozuContinuationStrategy(BaseStrategy):
    name = "Marubozu_Continuation"
    holding_period_bars = 5

    def prepare(self, df):
        candle_range = (df["high"] - df["low"]).replace(0, np.nan)
        body_ratio = (df["close"] - df["open"]).abs() / candle_range
        volume_ok = df["volume"] > df["volume"].rolling(20).mean()
        long_signal = (body_ratio > 0.72) & (df["close"] > df["open"]) & volume_ok
        short_signal = (body_ratio > 0.72) & (df["close"] < df["open"]) & volume_ok
        return apply_sided_levels(df, long_signal, short_signal, df["low"], df["high"])


class DoubleTopBottomBreakoutStrategy(BaseStrategy):
    name = "Double_Top_Bottom_Breakout"
    holding_period_bars = 12

    def prepare(self, df):
        tolerance = 0.015
        prior_low = df["low"].shift(5)
        recent_low = df["low"].shift(1)
        prior_high = df["high"].shift(5)
        recent_high = df["high"].shift(1)
        neckline_high = df["high"].rolling(5).max().shift(1)
        neckline_low = df["low"].rolling(5).min().shift(1)
        double_bottom = ((prior_low - recent_low).abs() / df["close"]) < tolerance
        double_top = ((prior_high - recent_high).abs() / df["close"]) < tolerance
        long_signal = double_bottom & (df["close"] > neckline_high)
        short_signal = double_top & (df["close"] < neckline_low)
        return apply_sided_levels(df, long_signal, short_signal, df["low"].rolling(8).min(), df["high"].rolling(8).max())
