from datetime import datetime, timedelta

import pandas as pd

from super_trader_quant.backend.app.strategies import STRATEGY_REGISTRY


ADDED_SETUP_NAMES = {
    "SMA20_50_Cross",
    "EMA9_21_Cross",
    "VWAP_Reclaim",
    "VWAP_Pullback",
    "NR7_Breakout",
    "Squeeze_Breakout",
    "Keltner_Breakout",
    "ADX_Trend_Pullback",
    "CCI_Reversal",
    "Stochastic_Cross",
    "WilliamsR_Reversal",
    "ROC_Momentum",
    "OBV_Breakout",
    "MFI_Reversal",
    "Gap_Continuation",
    "Gap_Fade",
    "Three_Bar_Reversal",
    "Pin_Bar_Reversal",
    "Marubozu_Continuation",
    "Double_Top_Bottom_Breakout",
}


def _sample_frame(rows: int = 90) -> pd.DataFrame:
    start = datetime(2026, 1, 1)
    data = []
    for index in range(rows):
        close = 100 + index * 0.25
        open_ = close - 0.15
        data.append(
            {
                "timestamp": start + timedelta(hours=index),
                "open": open_,
                "high": close + 1.0,
                "low": open_ - 1.0,
                "close": close,
                "volume": 100_000 + index * 1_000,
            }
        )
    return pd.DataFrame(data)


def test_strategy_registry_has_35_unique_setups():
    assert len(STRATEGY_REGISTRY) == 35
    assert len(set(STRATEGY_REGISTRY)) == 35
    assert ADDED_SETUP_NAMES.issubset(STRATEGY_REGISTRY)


def test_registered_strategies_prepare_required_columns_without_crashing():
    df = _sample_frame()

    for strategy_cls in STRATEGY_REGISTRY.values():
        prepared = strategy_cls().prepare(df.copy())
        assert {"signal", "side", "stop", "target"}.issubset(prepared.columns)
        assert set(prepared["side"].dropna().unique()).issubset({"long", "short"})
        assert len(prepared) == len(df)
