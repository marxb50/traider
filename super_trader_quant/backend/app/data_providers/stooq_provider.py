from io import StringIO
import pandas as pd
import requests
from .base import BaseProvider, attach_history_audit, normalize_history
from ..config import settings


class StooqProvider(BaseProvider):
    name = "stooq"

    def fetch_history(self, symbol: str, timeframe: str = "D1", period: str = "1y") -> pd.DataFrame:
        if timeframe != "D1":
            raise ValueError("Stooq MVP suporta apenas D1")
        if not settings.stooq_api_key:
            raise ValueError("STOOQ_API_KEY não configurada")
        normalized = symbol.lower().replace(".l", ".uk")
        url = f"https://stooq.com/q/d/l/?s={normalized}&i=d&apikey={settings.stooq_api_key}"
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        if response.text.startswith("Get your apikey:"):
            raise ValueError("STOOQ_API_KEY inválida ou ausente")
        df = pd.read_csv(StringIO(response.text))
        if df.empty or "Date" not in df.columns:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.rename(columns={"Date": "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        if period.endswith("y"):
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            years = int(period[:-1])
            cutoff = df["timestamp"].max() - pd.DateOffset(years=years)
            df = df[df["timestamp"] >= cutoff]
        return attach_history_audit(
            normalize_history(df),
            provider=self.name,
            symbol=symbol,
            timeframe=timeframe,
            period=period,
            source_url="https://stooq.com/q/d/l/",
        )
