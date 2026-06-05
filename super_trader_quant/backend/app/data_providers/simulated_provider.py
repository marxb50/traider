from __future__ import annotations
import hashlib
import numpy as np
import pandas as pd
from .base import BaseProvider, normalize_history


class SimulatedProvider(BaseProvider):
    name = "simulated"

    def fetch_history(self, symbol: str, timeframe: str = "D1", period: str = "1y") -> pd.DataFrame:
        normalized_timeframe = timeframe.upper()
        if normalized_timeframe in {"H1", "60M", "60MIN", "1H"}:
            bars = 520
            freq = "h"
        elif normalized_timeframe == "D1":
            bars = 260
            freq = "B"
        else:
            bars = 104
            freq = "W-FRI"
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        drift = rng.normal(0.0004, 0.0002)
        returns = rng.normal(drift, 0.02, size=bars)
        close = 100 * np.exp(np.cumsum(returns))
        open_ = close * (1 + rng.normal(0, 0.004, size=bars))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.02, size=bars))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.02, size=bars))
        volume = rng.integers(100_000, 2_000_000, size=bars)
        index = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=bars, freq=freq)
        return normalize_history(pd.DataFrame({
            "timestamp": index,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }))
