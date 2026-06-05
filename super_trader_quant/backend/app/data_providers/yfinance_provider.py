import pandas as pd
import yfinance as yf
from ..config import settings
from .base import BaseProvider, STANDARD_COLUMNS, attach_history_audit, normalize_history


class YFinanceProvider(BaseProvider):
    name = "yfinance"

    def __init__(self) -> None:
        cache_dir = settings.resolved_scheduler_lock_path.parent / "cache" / "py-yfinance"
        cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))

    def fetch_history(self, symbol: str, timeframe: str = "D1", period: str = "1y") -> pd.DataFrame:
        return self.fetch_many_history([symbol], timeframe=timeframe, period=period).get(
            symbol,
            pd.DataFrame(columns=STANDARD_COLUMNS),
        )

    def fetch_many_history(
        self,
        symbols: list[str],
        timeframe: str = "D1",
        period: str = "1y",
    ) -> dict[str, pd.DataFrame]:
        interval = {
            "H1": "60m",
            "60M": "60m",
            "60MIN": "60m",
            "1H": "60m",
            "D1": "1d",
            "W1": "1wk",
        }.get(timeframe.upper(), "1d")
        results: dict[str, pd.DataFrame] = {
            symbol: pd.DataFrame(columns=STANDARD_COLUMNS) for symbol in symbols
        }
        batch_size = 50
        for start in range(0, len(symbols), batch_size):
            batch = symbols[start : start + batch_size]
            data = yf.download(
                batch,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
                group_by="ticker",
            )
            if data.empty:
                continue
            for symbol in batch:
                try:
                    frame = data[symbol].copy() if isinstance(data.columns, pd.MultiIndex) else data.copy()
                except KeyError:
                    continue
                frame = frame.reset_index()
                if isinstance(frame.columns, pd.MultiIndex):
                    frame.columns = [column[-1] for column in frame.columns]
                frame = frame.rename(columns={frame.columns[0]: "timestamp"})
                results[symbol] = attach_history_audit(
                    normalize_history(frame),
                    provider=self.name,
                    symbol=symbol,
                    timeframe=timeframe,
                    period=period,
                    source_url="https://finance.yahoo.com/",
                    notes="yfinance nao oficial; usar apenas como prototipo/fallback",
                )
        return results
