from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    name: str
    holding_period_bars: int = 5

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError

    def latest_signal(self, df: pd.DataFrame) -> dict | None:
        prepared = self.prepare(df.copy())
        if prepared.empty or not bool(prepared.iloc[-1].get("signal", False)):
            return None
        row = prepared.iloc[-1]
        if pd.isna(row["stop"]) or pd.isna(row["target"]):
            return None
        side = str(row.get("side", "long")).lower()
        if side not in {"long", "short"}:
            side = "long"
        return {
            "signal_time": pd.Timestamp(row["timestamp"]).to_pydatetime(),
            "side": side,
            "entry": float(row["close"]),
            "stop": float(row["stop"]),
            "target": float(row["target"]),
            "holding_period_bars": self.holding_period_bars,
        }
