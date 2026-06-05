from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from ..strategies.utils import rsi
from .signal_quality_service import SignalQuality

INTRADAY_ENTRY_TIMEFRAMES = {"H1", "60M", "60MIN", "1H"}


@dataclass(frozen=True)
class TimeframeContext:
    timeframe: str
    trend: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MultiTimeframeContext:
    weekly: TimeframeContext
    daily: TimeframeContext
    aligned: bool
    strong_alignment: bool

    @property
    def summary(self) -> str:
        return (
            f"W1 {self.weekly.trend} ({self.weekly.score:.0f}/100), "
            f"D1 {self.daily.trend} ({self.daily.score:.0f}/100)"
        )


def context_timeframes_for_entry(timeframe: str) -> list[str]:
    if timeframe.upper() in INTRADAY_ENTRY_TIMEFRAMES:
        return ["W1", "D1"]
    return []


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _trend_context(df: pd.DataFrame, timeframe: str) -> TimeframeContext:
    if df is None or len(df) < 35:
        return TimeframeContext(
            timeframe=timeframe,
            trend="insuficiente",
            score=0.0,
            reasons=("historico insuficiente",),
        )

    close = df["close"].astype(float).reset_index(drop=True)
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    macd = _ema(close, 12) - _ema(close, 26)
    macd_signal = _ema(macd, 9)
    macd_hist = macd - macd_signal
    rsi14 = rsi(close, 14)

    last_close = float(close.iloc[-1])
    last_ema20 = float(ema20.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    ema20_slope = float(ema20.iloc[-1] - ema20.iloc[-4])
    macd_hist_slope = float(macd_hist.iloc[-1] - macd_hist.iloc[-4])
    last_rsi = float(rsi14.iloc[-1]) if pd.notna(rsi14.iloc[-1]) else 50.0

    points = 0
    reasons: list[str] = []

    if last_close > last_ema20:
        points += 1
        reasons.append("preco acima da EMA20")
    else:
        points -= 1
        reasons.append("preco abaixo da EMA20")

    if last_ema20 > last_ema50:
        points += 1
        reasons.append("EMA20 acima da EMA50")
    else:
        points -= 1
        reasons.append("EMA20 abaixo da EMA50")

    if ema20_slope > 0:
        points += 1
        reasons.append("EMA20 inclinada para cima")
    else:
        points -= 1
        reasons.append("EMA20 sem inclinacao positiva")

    if macd_hist_slope > 0:
        points += 1
        reasons.append("MACD histograma subindo")
    else:
        points -= 1
        reasons.append("MACD histograma caindo")

    if 45 <= last_rsi <= 75:
        points += 1
        reasons.append("RSI14 em zona saudavel")
    elif last_rsi < 40:
        points -= 1
        reasons.append("RSI14 fraco")
    elif last_rsi > 82:
        points -= 1
        reasons.append("RSI14 esticado")
    else:
        reasons.append("RSI14 neutro")

    score = round(max(0, min(100, ((points + 5) / 10) * 100)), 1)
    if points >= 3:
        trend = "bullish"
    elif points >= 1:
        trend = "neutro"
    else:
        trend = "bearish"
    return TimeframeContext(
        timeframe=timeframe,
        trend=trend,
        score=score,
        reasons=tuple(reasons[:3]),
    )


def analyze_multi_timeframe_context(context_frames: dict[str, pd.DataFrame]) -> MultiTimeframeContext:
    weekly = _trend_context(context_frames.get("W1", pd.DataFrame()), "W1")
    daily = _trend_context(context_frames.get("D1", pd.DataFrame()), "D1")
    aligned = weekly.trend in {"bullish", "neutro"} and daily.trend in {"bullish", "neutro"}
    strong_alignment = weekly.trend == "bullish" and daily.trend == "bullish"
    return MultiTimeframeContext(
        weekly=weekly,
        daily=daily,
        aligned=aligned,
        strong_alignment=strong_alignment,
    )


def apply_multi_timeframe_filter(
    quality: SignalQuality,
    context: MultiTimeframeContext | None,
    *,
    side: str = "long",
) -> SignalQuality:
    if context is None:
        return quality

    mtf_note = f"contexto MTF: {context.summary}"
    side_normalized = (side or "long").lower()
    if side_normalized == "short":
        aligned = context.weekly.trend in {"bearish", "neutro"} and context.daily.trend in {"bearish", "neutro"}
        strong_alignment = context.weekly.trend == "bearish" and context.daily.trend == "bearish"
        direction_label = "venda"
    else:
        aligned = context.aligned
        strong_alignment = context.strong_alignment
        direction_label = "compra"

    if not aligned:
        return replace(
            quality,
            level="red",
            score=min(quality.score, 49.0),
            reason=f"{quality.reason}; {mtf_note}; bloqueado por tendencia maior para {direction_label}",
        )

    if quality.level == "green" and not strong_alignment:
        return replace(
            quality,
            level="yellow",
            score=min(quality.score, 74.0),
            reason=f"{quality.reason}; {mtf_note}; alinhamento parcial para {direction_label}",
        )

    return replace(
        quality,
        reason=f"{quality.reason}; {mtf_note}; alinhado para {direction_label}",
    )
