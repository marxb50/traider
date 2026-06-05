from __future__ import annotations
import logging
from sqlmodel import Session, select
from ..config import settings
from ..models.asset import Asset
from ..models.signal import Signal
from ..strategies import STRATEGY_REGISTRY
from ..services.notification_service import enqueue_notification
from ..services.multi_timeframe_service import (
    analyze_multi_timeframe_context,
    apply_multi_timeframe_filter,
    context_timeframes_for_entry,
)
from ..services.data_source_audit_service import (
    apply_data_source_filter,
    evaluate_data_source_check,
)
from ..services.signal_quality_service import (
    analyze_signal_quality,
    format_signal_opened_message,
    format_signal_resolved_message,
    is_alert_level_enabled,
)
from ..time_utils import utc_now_naive
from .memory_engine import update_memory_from_signal

logger = logging.getLogger(__name__)


def _is_market_allowed(market: str) -> bool:
    allowed_markets = settings.scan_market_list
    if not allowed_markets:
        return True
    return market.upper() in allowed_markets


def _fetch_many(provider, symbols: list[str], timeframe: str, period: str):
    if hasattr(provider, "fetch_many_history"):
        return provider.fetch_many_history(symbols, timeframe=timeframe, period=period)
    return {
        symbol: provider.fetch_history(symbol, timeframe=timeframe, period=period)
        for symbol in symbols
    }


def _history_period_for_timeframe(timeframe: str) -> str:
    timeframe_upper = timeframe.upper()
    if timeframe_upper in {"H1", "60M", "60MIN", "1H"}:
        return settings.scan_intraday_period
    if timeframe_upper == "W1":
        return settings.scan_weekly_period
    return settings.scan_daily_period


def _signal_pnl_pct(side: str, entry_price: float, exit_price: float) -> float:
    if side == "short":
        return ((entry_price / exit_price) - 1) * 100
    return ((exit_price / entry_price) - 1) * 100


def scan_assets(session: Session, provider, timeframe: str = "D1", symbols: list[str] | None = None) -> list[Signal]:
    assets = session.exec(select(Asset).where(Asset.active == True)).all()  # noqa: E712
    assets = [asset for asset in assets if _is_market_allowed(asset.market)]
    if symbols:
        assets = [asset for asset in assets if asset.symbol in symbols]
    history_period = _history_period_for_timeframe(timeframe)
    histories = _fetch_many(
        provider,
        [asset.symbol for asset in assets],
        timeframe=timeframe,
        period=history_period,
    )
    context_histories_by_timeframe = {
        context_timeframe: _fetch_many(
            provider,
            [asset.symbol for asset in assets],
            timeframe=context_timeframe,
            period=_history_period_for_timeframe(context_timeframe),
        )
        for context_timeframe in context_timeframes_for_entry(timeframe)
    }
    created: list[Signal] = []
    for asset in assets:
        try:
            df = histories.get(asset.symbol)
            if df is None:
                continue
            if df.empty:
                continue
            for strategy_cls in STRATEGY_REGISTRY.values():
                strategy = strategy_cls()
                payload = strategy.latest_signal(df)
                if not payload:
                    continue
                existing = session.exec(select(Signal).where(
                    Signal.asset_symbol == asset.symbol,
                    Signal.strategy == strategy.name,
                    Signal.timeframe == timeframe,
                    Signal.signal_time == payload["signal_time"],
                )).first()
                if existing:
                    continue
                quality = analyze_signal_quality(df, strategy, payload)
                mtf_context = None
                if context_histories_by_timeframe:
                    mtf_context = analyze_multi_timeframe_context(
                        {
                            context_timeframe: histories_for_timeframe.get(asset.symbol)
                            for context_timeframe, histories_for_timeframe in context_histories_by_timeframe.items()
                        }
                    )
                    quality = apply_multi_timeframe_filter(
                        quality,
                        mtf_context,
                        side=payload.get("side", "long"),
                    )
                data_source_check = evaluate_data_source_check(
                    provider,
                    symbol=asset.symbol,
                    market=asset.market,
                    timeframe=timeframe,
                    period=history_period,
                    primary_df=df,
                )
                quality = apply_data_source_filter(quality, data_source_check)
                signal = Signal(
                    asset_symbol=asset.symbol,
                    market=asset.market,
                    strategy=strategy.name,
                    timeframe=timeframe,
                    signal_time=payload["signal_time"],
                    side=payload.get("side", "long"),
                    entry=payload["entry"],
                    stop=payload["stop"],
                    target=payload["target"],
                    holding_period_bars=payload["holding_period_bars"],
                    alert_level=quality.level,
                    alert_score=quality.score,
                    alert_probability_pct=quality.probability_pct,
                    alert_sample_size=quality.sample_size,
                    alert_avg_bars_to_target=quality.avg_bars_to_target,
                    alert_risk_reward=quality.risk_reward,
                    alert_reason=quality.reason,
                    data_provider=data_source_check.primary_provider,
                    data_source_status=data_source_check.status,
                    data_source_count=data_source_check.source_count,
                    data_source_reason=data_source_check.reason,
                    data_source_audit_json=data_source_check.to_json(),
                )
                session.add(signal)
                session.flush()
                if is_alert_level_enabled(quality.level):
                    enqueue_notification(
                        session,
                        kind="signal_opened",
                        dedupe_key=f"signal_opened:{signal.id}",
                        message=format_signal_opened_message(signal, quality),
                        market=signal.market,
                    )
                else:
                    signal.notes = f"alert_suppressed:{quality.level}:{quality.reason}"
                    session.add(signal)
                session.commit()
                session.refresh(signal)
                created.append(signal)
        except Exception:
            logger.exception("Falha ao escanear %s", asset.symbol)
    return created


def resolve_open_signals(session: Session, provider) -> list[Signal]:
    open_signals = session.exec(select(Signal).where(Signal.status == "open")).all()
    now = utc_now_naive()
    histories_by_timeframe: dict[str, dict[str, object]] = {}
    for timeframe in sorted({signal.timeframe for signal in open_signals}):
        symbols_for_timeframe = sorted(
            {signal.asset_symbol for signal in open_signals if signal.timeframe == timeframe}
        )
        histories_by_timeframe[timeframe] = _fetch_many(
            provider,
            symbols_for_timeframe,
            timeframe=timeframe,
            period=_history_period_for_timeframe(timeframe),
        )
    resolved: list[Signal] = []
    for signal in open_signals:
        try:
            df = histories_by_timeframe.get(signal.timeframe, {}).get(signal.asset_symbol)
            if df is None or df.empty:
                continue
            after_signal = df[df["timestamp"] > signal.signal_time].reset_index(drop=True)
            max_bars = min(signal.holding_period_bars, len(after_signal))
            outcome = None
            exit_price = None
            exit_time = None
            if after_signal.empty:
                signal_age_days = (now - signal.signal_time).total_seconds() / 86400
                last_bar = df.iloc[-1]
                last_timestamp = last_bar["timestamp"]
                last_timestamp_py = (
                    last_timestamp.to_pydatetime()
                    if hasattr(last_timestamp, "to_pydatetime")
                    else last_timestamp
                )
                if (
                    signal_age_days <= settings.max_open_signal_age_days
                    or last_timestamp_py > signal.signal_time
                ):
                    continue
                outcome = "expired"
                entry_price = float(signal.entry)
                exit_price = float(last_bar["close"])
                exit_time = last_timestamp
                note = "expired_without_post_signal_data"
                signal.notes = f"{signal.notes} | {note}" if signal.notes else note
            else:
                entry_price = float(after_signal.iloc[0]["open"])
                side = (signal.side or "long").lower()
                for i in range(max_bars):
                    bar = after_signal.iloc[i]
                    if side == "short":
                        if float(bar["high"]) >= signal.stop:
                            outcome = "failure"
                            exit_price = signal.stop
                            exit_time = bar["timestamp"]
                            break
                        if float(bar["low"]) <= signal.target:
                            outcome = "success"
                            exit_price = signal.target
                            exit_time = bar["timestamp"]
                            break
                    else:
                        if float(bar["low"]) <= signal.stop:
                            outcome = "failure"
                            exit_price = signal.stop
                            exit_time = bar["timestamp"]
                            break
                        if float(bar["high"]) >= signal.target:
                            outcome = "success"
                            exit_price = signal.target
                            exit_time = bar["timestamp"]
                            break
                if outcome is None and len(after_signal) >= signal.holding_period_bars:
                    final_bar = after_signal.iloc[signal.holding_period_bars - 1]
                    outcome = "expired"
                    exit_price = float(final_bar["close"])
                    exit_time = final_bar["timestamp"]
            if outcome is None:
                continue
            signal.status = outcome
            signal.exit_price = float(exit_price)
            signal.exit_time = exit_time.to_pydatetime() if hasattr(exit_time, "to_pydatetime") else exit_time
            signal.pnl_pct = _signal_pnl_pct((signal.side or "long").lower(), entry_price, signal.exit_price)
            signal.outcome_checked_at = now
            session.add(signal)
            update_memory_from_signal(session, signal)
            if _is_market_allowed(signal.market) and is_alert_level_enabled(signal.alert_level):
                enqueue_notification(
                    session,
                    kind="signal_resolved",
                    dedupe_key=f"signal_resolved:{signal.id}",
                    message=format_signal_resolved_message(signal),
                    market=signal.market,
                )
            session.commit()
            session.refresh(signal)
            resolved.append(signal)
        except Exception:
            logger.exception("Falha ao resolver sinal %s", signal.id)
    return resolved
