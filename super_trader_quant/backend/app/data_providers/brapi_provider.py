from __future__ import annotations

import pandas as pd
import requests

from ..config import settings
from .base import BaseProvider, STANDARD_COLUMNS, attach_history_audit, normalize_history


BRAPI_PUBLIC_TEST_TICKERS = {"PETR4", "MGLU3", "VALE3", "ITUB4"}


def normalize_brapi_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SA"):
        normalized = normalized[:-3]
    return normalized


def brapi_can_fetch_without_token(symbol: str) -> bool:
    return normalize_brapi_symbol(symbol) in BRAPI_PUBLIC_TEST_TICKERS


def _interval_for_timeframe(timeframe: str) -> str:
    timeframe_upper = timeframe.upper()
    if timeframe_upper in {"H1", "60M", "60MIN", "1H"}:
        return "1h"
    if timeframe_upper == "W1":
        return "1wk"
    return "1d"


def _range_for_period(period: str) -> str:
    normalized = period.strip().lower()
    return normalized or "1y"


class BrapiProvider(BaseProvider):
    name = "brapi"

    def fetch_history(self, symbol: str, timeframe: str = "D1", period: str = "1y") -> pd.DataFrame:
        ticker = normalize_brapi_symbol(symbol)
        token = settings.brapi_token.strip()
        if not token and not brapi_can_fetch_without_token(ticker):
            raise ValueError("BRAPI_TOKEN nao configurado para este ticker")

        base_url = settings.brapi_base_url.rstrip("/")
        url = f"{base_url}/quote/{ticker}"
        params = {
            "range": _range_for_period(period),
            "interval": _interval_for_timeframe(timeframe),
        }
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        historical_prices = results[0].get("historicalDataPrice") or []
        rows = []
        for item in historical_prices:
            raw_date = item.get("date")
            if raw_date is None:
                continue
            if isinstance(raw_date, (int, float)):
                timestamp = pd.to_datetime(raw_date, unit="s", utc=True)
            else:
                timestamp = pd.to_datetime(raw_date, utc=True)
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": item.get("volume", 0),
                }
            )

        return attach_history_audit(
            normalize_history(pd.DataFrame(rows)),
            provider=self.name,
            symbol=symbol,
            timeframe=timeframe,
            period=period,
            source_url=f"{base_url}/quote/{ticker}",
        )

