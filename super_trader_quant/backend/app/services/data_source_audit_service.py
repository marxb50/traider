from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json

import pandas as pd

from ..config import settings
from ..data_providers.brapi_provider import brapi_can_fetch_without_token
from .signal_quality_service import SignalQuality


IMPORTANT_LEVELS = {"yellow", "green"}


@dataclass(frozen=True)
class DataSourceCheck:
    status: str
    confirmed: bool
    blocks_alert: bool
    source_count: int
    primary_provider: str
    confirmation_provider: str | None
    reason: str
    primary_last_timestamp: str | None = None
    confirmation_last_timestamp: str | None = None
    primary_last_close: float | None = None
    confirmation_last_close: float | None = None
    close_diff_pct: float | None = None

    @property
    def summary(self) -> str:
        providers = self.primary_provider
        if self.confirmation_provider:
            providers = f"{providers}+{self.confirmation_provider}"
        diff = ""
        if self.close_diff_pct is not None:
            diff = f", dif. close {self.close_diff_pct:.2f}%"
        return f"{self.status} ({providers}, {self.source_count} fonte(s){diff}): {self.reason}"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True)


def _provider_name(provider) -> str:
    return str(getattr(provider, "name", provider.__class__.__name__)).lower()


def _last_snapshot(df: pd.DataFrame | None) -> tuple[str | None, float | None, pd.Timestamp | None]:
    if df is None or df.empty:
        return None, None, None
    last_row = df.iloc[-1]
    timestamp = pd.Timestamp(last_row["timestamp"])
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    close = float(last_row["close"])
    return timestamp.isoformat(), close, timestamp


def _timestamps_match(
    primary_timestamp: pd.Timestamp | None,
    confirmation_timestamp: pd.Timestamp | None,
    timeframe: str,
) -> bool:
    if primary_timestamp is None or confirmation_timestamp is None:
        return False
    timeframe_upper = timeframe.upper()
    if timeframe_upper in {"D1", "W1"}:
        return primary_timestamp.date() == confirmation_timestamp.date()
    drift_hours = abs((primary_timestamp - confirmation_timestamp).total_seconds()) / 3600
    return drift_hours <= settings.signal_data_confirmation_max_timestamp_drift_hours


def _close_diff_pct(primary_close: float | None, confirmation_close: float | None) -> float | None:
    if primary_close is None or confirmation_close is None or primary_close == 0:
        return None
    return abs((confirmation_close / primary_close) - 1) * 100


def _can_try_confirmation(provider_name: str, symbol: str) -> bool:
    if provider_name != "brapi":
        return True
    return bool(settings.brapi_token.strip()) or brapi_can_fetch_without_token(symbol)


def evaluate_data_source_check(
    provider,
    *,
    symbol: str,
    market: str,
    timeframe: str,
    period: str,
    primary_df: pd.DataFrame,
) -> DataSourceCheck:
    mode = settings.signal_data_confirmation_mode_normalized
    primary_provider = _provider_name(provider)
    primary_timestamp, primary_close, primary_timestamp_obj = _last_snapshot(primary_df)
    base = {
        "primary_provider": primary_provider,
        "primary_last_timestamp": primary_timestamp,
        "primary_last_close": primary_close,
    }

    if mode == "off":
        return DataSourceCheck(
            status="skipped",
            confirmed=True,
            blocks_alert=False,
            source_count=1,
            confirmation_provider=None,
            reason="confirmacao desligada por configuracao",
            **base,
        )

    if primary_provider == "simulated":
        return DataSourceCheck(
            status="skipped",
            confirmed=True,
            blocks_alert=False,
            source_count=1,
            confirmation_provider=None,
            reason="provider simulado usado apenas para teste",
            **base,
        )

    allowed_markets = settings.signal_data_confirmation_market_list
    if allowed_markets and market.upper() not in allowed_markets:
        return DataSourceCheck(
            status="skipped",
            confirmed=True,
            blocks_alert=False,
            source_count=1,
            confirmation_provider=None,
            reason=f"mercado {market} fora da lista de confirmacao",
            **base,
        )

    confirmation_provider_name = settings.signal_data_confirmation_provider.strip().lower()
    if not confirmation_provider_name or confirmation_provider_name == primary_provider:
        return DataSourceCheck(
            status="primary_only",
            confirmed=mode != "strict",
            blocks_alert=mode == "strict",
            source_count=1,
            confirmation_provider=confirmation_provider_name or None,
            reason="sem provider secundario diferente da fonte principal",
            **base,
        )

    if not _can_try_confirmation(confirmation_provider_name, symbol):
        return DataSourceCheck(
            status="unconfigured",
            confirmed=False,
            blocks_alert=mode == "strict",
            source_count=1,
            confirmation_provider=confirmation_provider_name,
            reason=f"{confirmation_provider_name.upper()} exige token para {symbol}",
            **base,
        )

    try:
        from ..data_providers.factory import get_provider

        confirmation_provider = get_provider(confirmation_provider_name)
        confirmation_df = confirmation_provider.fetch_history(symbol, timeframe=timeframe, period=period)
    except Exception as exc:  # noqa: BLE001
        return DataSourceCheck(
            status="unavailable",
            confirmed=False,
            blocks_alert=mode == "strict",
            source_count=1,
            confirmation_provider=confirmation_provider_name,
            reason=f"falha ao consultar fonte secundaria: {exc}",
            **base,
        )

    confirmation_timestamp, confirmation_close, confirmation_timestamp_obj = _last_snapshot(confirmation_df)
    if confirmation_df.empty:
        return DataSourceCheck(
            status="unavailable",
            confirmed=False,
            blocks_alert=mode == "strict",
            source_count=1,
            confirmation_provider=confirmation_provider_name,
            reason="fonte secundaria retornou historico vazio",
            **base,
        )

    timestamp_ok = _timestamps_match(primary_timestamp_obj, confirmation_timestamp_obj, timeframe)
    close_diff_pct = _close_diff_pct(primary_close, confirmation_close)
    close_ok = (
        close_diff_pct is not None
        and close_diff_pct <= settings.signal_data_confirmation_max_close_diff_pct
    )
    confirmed = timestamp_ok and close_ok
    status = "confirmed" if confirmed else "mismatch"
    reason = (
        "ultimo candle e preco confirmados por fonte secundaria"
        if confirmed
        else "fonte secundaria divergiu em data do candle ou preco"
    )
    return DataSourceCheck(
        status=status,
        confirmed=confirmed,
        blocks_alert=not confirmed,
        source_count=2,
        confirmation_provider=confirmation_provider_name,
        reason=reason,
        confirmation_last_timestamp=confirmation_timestamp,
        confirmation_last_close=confirmation_close,
        close_diff_pct=round(close_diff_pct, 4) if close_diff_pct is not None else None,
        **base,
    )


def apply_data_source_filter(quality: SignalQuality, check: DataSourceCheck) -> SignalQuality:
    note = f"auditoria dados: {check.summary}"
    if check.blocks_alert and quality.level in IMPORTANT_LEVELS:
        return replace(
            quality,
            level="red",
            score=min(quality.score, 49.0),
            reason=f"{quality.reason}; {note}; verde/amarelo bloqueado sem quorum de dados",
        )
    return replace(quality, reason=f"{quality.reason}; {note}")

