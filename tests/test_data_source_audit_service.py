from datetime import datetime

import pandas as pd

from super_trader_quant.backend.app.services.data_source_audit_service import (
    apply_data_source_filter,
    evaluate_data_source_check,
)
from super_trader_quant.backend.app.services.signal_quality_service import SignalQuality


class PrimaryProvider:
    name = "yfinance"


class MatchingConfirmationProvider:
    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        return _frame(close=100.2)


class DivergentConfirmationProvider:
    def fetch_history(self, symbol, timeframe="D1", period="1y"):
        return _frame(close=104.0)


def _frame(close: float = 100.0):
    return pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 6, 1),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1,
            }
        ]
    )


def _green_quality():
    return SignalQuality(
        level="green",
        score=88.0,
        probability_pct=70.0,
        sample_size=20,
        successes=14,
        failures=3,
        expired=3,
        avg_pnl_pct=1.1,
        avg_bars_to_target=2.0,
        risk_reward=2.0,
        target_pct=4.0,
        stop_pct=-2.0,
        reason="historico forte",
    )


def test_data_source_confirmation_keeps_green_when_sources_match(monkeypatch):
    from super_trader_quant.backend.app.data_providers import factory

    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_mode", "strict")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_provider", "brapi")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_markets", "BR")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.brapi_token", "token-123")
    monkeypatch.setattr(factory, "get_provider", lambda _name: MatchingConfirmationProvider())

    check = evaluate_data_source_check(
        PrimaryProvider(),
        symbol="PETR4.SA",
        market="BR",
        timeframe="D1",
        period="1y",
        primary_df=_frame(close=100.0),
    )
    quality = apply_data_source_filter(_green_quality(), check)

    assert check.status == "confirmed"
    assert check.source_count == 2
    assert quality.level == "green"


def test_data_source_confirmation_blocks_green_when_sources_diverge(monkeypatch):
    from super_trader_quant.backend.app.data_providers import factory

    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_mode", "strict")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_provider", "brapi")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_markets", "BR")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.brapi_token", "token-123")
    monkeypatch.setattr(factory, "get_provider", lambda _name: DivergentConfirmationProvider())

    check = evaluate_data_source_check(
        PrimaryProvider(),
        symbol="PETR4.SA",
        market="BR",
        timeframe="D1",
        period="1y",
        primary_df=_frame(close=100.0),
    )
    quality = apply_data_source_filter(_green_quality(), check)

    assert check.status == "mismatch"
    assert check.blocks_alert is True
    assert quality.level == "red"
    assert "verde/amarelo bloqueado sem quorum" in quality.reason


def test_auto_mode_does_not_block_when_brapi_token_is_missing(monkeypatch):
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_mode", "auto")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_provider", "brapi")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.signal_data_confirmation_markets", "BR")
    monkeypatch.setattr("super_trader_quant.backend.app.services.data_source_audit_service.settings.brapi_token", "")

    check = evaluate_data_source_check(
        PrimaryProvider(),
        symbol="WEGE3.SA",
        market="BR",
        timeframe="D1",
        period="1y",
        primary_df=_frame(close=100.0),
    )
    quality = apply_data_source_filter(_green_quality(), check)

    assert check.status == "unconfigured"
    assert check.blocks_alert is False
    assert quality.level == "green"

