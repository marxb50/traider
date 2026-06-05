from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

import pandas as pd

from ..config import settings
from ..engine.backtester import run_backtest

ALERT_LEVEL_ORDER = {"red": 0, "yellow": 1, "green": 2}
ALERT_LEVEL_LABELS = {"red": "VERMELHO", "yellow": "AMARELO", "green": "VERDE"}
TIMEFRAME_DESCRIPTIONS = {
    "H1": "H1/60 minutos: 1 candle = 1 hora de negociacao",
    "60M": "60 minutos: 1 candle = 1 hora de negociacao",
    "60MIN": "60 minutos: 1 candle = 1 hora de negociacao",
    "1H": "1 hora: 1 candle = 1 hora de negociacao",
    "D1": "D1 diario: 1 candle = 1 pregao/dia util",
    "W1": "W1 semanal: 1 candle = 1 semana",
}


@dataclass(frozen=True)
class SignalQuality:
    level: str
    score: float
    probability_pct: float
    sample_size: int
    successes: int
    failures: int
    expired: int
    avg_pnl_pct: float
    avg_bars_to_target: float | None
    risk_reward: float
    target_pct: float
    stop_pct: float
    reason: str

    @property
    def label(self) -> str:
        return ALERT_LEVEL_LABELS[self.level]


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(value, maximum))


def _safe_round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _risk_reward(entry: float, stop: float, target: float, side: str = "long") -> float:
    if side == "short":
        risk = max(stop - entry, 0.0)
        reward = max(entry - target, 0.0)
    else:
        risk = max(entry - stop, 0.0)
        reward = max(target - entry, 0.0)
    if risk <= 0:
        return 0.0
    return reward / risk


def _side_label(side: str) -> str:
    return "VENDA" if side == "short" else "COMPRA"


def describe_timeframe(timeframe: str) -> str:
    return TIMEFRAME_DESCRIPTIONS.get(
        timeframe.upper(),
        f"{timeframe}: unidade do candle depende da configuracao do provedor",
    )


def _format_bars_duration(bars: float | int | None, timeframe: str) -> str:
    if bars is None:
        return "n/d"
    bars_value = float(bars)
    bars_label = f"{bars_value:.1f} candles"
    timeframe_upper = timeframe.upper()
    if timeframe_upper == "D1":
        return f"{bars_label} D1 (~{bars_value:.1f} pregoes/dias uteis)"
    if timeframe_upper == "W1":
        return f"{bars_label} W1 (~{bars_value:.1f} semanas)"
    if timeframe_upper in {"H1", "60M", "60MIN", "1H"}:
        return f"{bars_label} H1 (~{bars_value:.1f} horas de negociacao)"
    return f"{bars_label} {timeframe}"


def _format_data_source_line(signal) -> str | None:
    status = getattr(signal, "data_source_status", None)
    if not status:
        return None
    provider = getattr(signal, "data_provider", None) or "n/d"
    source_count = getattr(signal, "data_source_count", None)
    reason = getattr(signal, "data_source_reason", None) or "sem detalhe"
    return f"dados: {status} | provider: {provider} | fontes: {source_count} | {reason}"


def _bayesian_probability(successes: int, total: int) -> float:
    prior_weight = max(settings.signal_alert_prior_weight, 0.0)
    prior_successes = 0.5 * prior_weight
    return (successes + prior_successes) / (total + prior_weight) if total + prior_weight > 0 else 0.5


def _score_quality(
    *,
    probability: float,
    sample_size: int,
    avg_pnl_pct: float,
    risk_reward: float,
) -> float:
    sample_score = _clamp(sample_size / max(settings.signal_alert_green_min_sample_size, 1))
    pnl_score = _clamp((avg_pnl_pct + 1.0) / 3.0)
    rr_score = _clamp((risk_reward - 1.0) / 1.5)
    return round(100 * ((0.55 * probability) + (0.2 * sample_score) + (0.15 * pnl_score) + (0.1 * rr_score)), 1)


def _level_for_quality(
    *,
    probability: float,
    sample_size: int,
    avg_pnl_pct: float,
    risk_reward: float,
) -> tuple[str, str]:
    if (
        sample_size >= settings.signal_alert_green_min_sample_size
        and probability >= settings.signal_alert_green_min_probability
        and avg_pnl_pct >= settings.signal_alert_green_min_avg_pnl_pct
        and risk_reward >= settings.signal_alert_min_risk_reward
    ):
        return "green", "historico forte no ativo/setup"
    if (
        sample_size >= settings.signal_alert_yellow_min_sample_size
        and probability >= settings.signal_alert_yellow_min_probability
        and avg_pnl_pct >= settings.signal_alert_yellow_min_avg_pnl_pct
        and risk_reward >= settings.signal_alert_min_risk_reward
    ):
        return "yellow", "historico aceitavel, mas com cautela"
    return "red", "historico insuficiente ou estatistica fraca"


def is_alert_level_enabled(level: str | None) -> bool:
    if level is None:
        return False
    min_level = settings.signal_alert_min_level_normalized
    if min_level not in ALERT_LEVEL_ORDER:
        min_level = "yellow"
    return ALERT_LEVEL_ORDER.get(level, -1) >= ALERT_LEVEL_ORDER[min_level]


def analyze_signal_quality(df: pd.DataFrame, strategy, payload: dict) -> SignalQuality:
    entry = float(payload["entry"])
    stop = float(payload["stop"])
    target = float(payload["target"])
    side = str(payload.get("side", "long")).lower()
    risk_reward = _risk_reward(entry, stop, target, side=side)
    target_pct = ((target / entry) - 1) * 100 if entry else 0.0
    stop_pct = ((stop / entry) - 1) * 100 if entry else 0.0

    signal_time = pd.Timestamp(payload["signal_time"])
    historical_df = df[pd.to_datetime(df["timestamp"]) < signal_time].copy()
    if hasattr(strategy, "prepare") and not historical_df.empty:
        trades, _ = run_backtest(historical_df, strategy)
    else:
        trades = []
    sample_size = len(trades)
    successes = sum(trade["outcome"] == "success" for trade in trades)
    failures = sum(trade["outcome"] == "failure" for trade in trades)
    expired = sum(trade["outcome"] == "expired" for trade in trades)
    avg_pnl_pct = mean([float(trade["return_pct"]) for trade in trades]) if trades else 0.0
    success_bars = [int(trade["bars_held"]) for trade in trades if trade["outcome"] == "success"]
    avg_bars_to_target = mean(success_bars) if success_bars else None
    probability = _bayesian_probability(successes, sample_size)
    level, reason = _level_for_quality(
        probability=probability,
        sample_size=sample_size,
        avg_pnl_pct=avg_pnl_pct,
        risk_reward=risk_reward,
    )
    score = _score_quality(
        probability=probability,
        sample_size=sample_size,
        avg_pnl_pct=avg_pnl_pct,
        risk_reward=risk_reward,
    )
    return SignalQuality(
        level=level,
        score=score,
        probability_pct=round(probability * 100, 1),
        sample_size=sample_size,
        successes=successes,
        failures=failures,
        expired=expired,
        avg_pnl_pct=round(avg_pnl_pct, 2),
        avg_bars_to_target=_safe_round(avg_bars_to_target, 1),
        risk_reward=round(risk_reward, 2),
        target_pct=round(target_pct, 2),
        stop_pct=round(stop_pct, 2),
        reason=reason,
    )


def format_signal_opened_message(signal, quality: SignalQuality) -> str:
    avg_bars = (
        _format_bars_duration(quality.avg_bars_to_target, signal.timeframe)
        if quality.avg_bars_to_target is not None
        else "sem alvo historico"
    )
    max_window = _format_bars_duration(signal.holding_period_bars, signal.timeframe)
    side = (getattr(signal, "side", "long") or "long").lower()
    lines = [
        f"[SUPER_TRADER_QUANT] ALERTA {quality.label} {_side_label(side)} | {signal.strategy} em {signal.asset_symbol} ({signal.timeframe})",
        f"timeframe: {describe_timeframe(signal.timeframe)}",
        f"chance de acerto historica estimada: {quality.probability_pct:.1f}% | score: {quality.score:.1f}/100 | amostra: {quality.sample_size}",
        f"historico setup/ativo: {quality.successes} alvo, {quality.failures} stop, {quality.expired} expirado | pnl medio: {quality.avg_pnl_pct:.2f}%",
        f"tempo medio ate alvo: {avg_bars} | janela maxima: {max_window}",
        f"entrada ref.: {signal.entry:.2f} | stop: {signal.stop:.2f} ({quality.stop_pct:+.2f}%) | alvo: {signal.target:.2f} ({quality.target_pct:+.2f}%) | RR: {quality.risk_reward:.2f}",
    ]
    data_source_line = _format_data_source_line(signal)
    if data_source_line:
        lines.append(data_source_line)
    lines.append(f"leitura tecnica: {quality.reason} | SIMULACAO - NAO E CONTA REAL")
    return "\n".join(lines)


def format_signal_resolved_message(signal) -> str:
    level = ALERT_LEVEL_LABELS.get(signal.alert_level or "", "NAO CLASSIFICADO")
    probability = f"{signal.alert_probability_pct:.1f}%" if signal.alert_probability_pct is not None else "n/d"
    avg_bars = (
        _format_bars_duration(signal.alert_avg_bars_to_target, signal.timeframe)
        if signal.alert_avg_bars_to_target is not None
        else "n/d"
    )
    return "\n".join(
        [
            f"[SUPER_TRADER_QUANT] Sinal resolvido {_side_label((getattr(signal, 'side', 'long') or 'long').lower())} {signal.strategy} em {signal.asset_symbol}: {signal.status.upper()}",
            f"timeframe: {describe_timeframe(signal.timeframe)}",
            f"alerta original: {level} | chance de acerto historica: {probability} | tempo medio alvo: {avg_bars}",
            f"resultado: {signal.pnl_pct:.2f}% | SIMULACAO",
        ]
    )
