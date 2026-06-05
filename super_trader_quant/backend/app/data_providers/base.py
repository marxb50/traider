from abc import ABC, abstractmethod
from datetime import datetime, timezone
import pandas as pd


STANDARD_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    normalized = df.copy()
    normalized.columns = [str(column).lower() for column in normalized.columns]
    if "timestamp" not in normalized.columns:
        date_col = "datetime" if "datetime" in normalized.columns else normalized.columns[0]
        normalized = normalized.rename(columns={date_col: "timestamp"})
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True).dt.tz_localize(None)
    return normalized[STANDARD_COLUMNS].dropna().sort_values("timestamp").reset_index(drop=True)


def attach_history_audit(
    df: pd.DataFrame,
    *,
    provider: str,
    symbol: str,
    timeframe: str,
    period: str,
    source_url: str | None = None,
    notes: str | None = None,
) -> pd.DataFrame:
    audited = df.copy()
    last_timestamp = None
    last_close = None
    if not audited.empty:
        last_row = audited.iloc[-1]
        timestamp = pd.Timestamp(last_row["timestamp"])
        last_timestamp = timestamp.isoformat()
        last_close = float(last_row["close"])
    audited.attrs["source_audit"] = {
        "provider": provider,
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "source_url": source_url,
        "rows": int(len(audited)),
        "last_timestamp": last_timestamp,
        "last_close": last_close,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "notes": notes,
    }
    return audited


class BaseProvider(ABC):
    name: str

    @abstractmethod
    def fetch_history(self, symbol: str, timeframe: str = "D1", period: str = "1y") -> pd.DataFrame:
        raise NotImplementedError

    def fetch_many_history(
        self,
        symbols: list[str],
        timeframe: str = "D1",
        period: str = "1y",
    ) -> dict[str, pd.DataFrame]:
        return {
            symbol: self.fetch_history(symbol, timeframe=timeframe, period=period)
            for symbol in symbols
        }
