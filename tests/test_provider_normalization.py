import pandas as pd
from super_trader_quant.backend.app.data_providers.base import normalize_history


def test_normalize_history_returns_tz_naive_timestamps():
    df = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-05-15T00:00:00Z"),
                "Open": 1,
                "High": 2,
                "Low": 0.5,
                "Close": 1.5,
                "Volume": 10,
            }
        ]
    )
    normalized = normalize_history(df)
    assert normalized["timestamp"].dt.tz is None
    assert normalized.iloc[0]["timestamp"] == pd.Timestamp("2026-05-15")
