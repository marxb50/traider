from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import requests

from ..config import settings


def _format_bcb_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.strftime("%d/%m/%Y")


def _parse_bcb_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", "."))


class BCBSgsProvider:
    name = "bcb_sgs"

    def fetch_series(
        self,
        series_id: int | str,
        *,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> pd.DataFrame:
        base_url = settings.bcb_sgs_base_url.rstrip("/")
        url = f"{base_url}.{series_id}/dados"
        params = {"formato": "json"}
        start_text = _format_bcb_date(start)
        end_text = _format_bcb_date(end)
        if start_text:
            params["dataInicial"] = start_text
        if end_text:
            params["dataFinal"] = end_text

        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        rows = []
        for item in response.json():
            rows.append(
                {
                    "timestamp": pd.to_datetime(item["data"], format="%d/%m/%Y"),
                    "value": _parse_bcb_value(item["valor"]),
                }
            )
        return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)

    def fetch_latest(self, series_id: int | str) -> dict[str, object] | None:
        frame = self.fetch_series(series_id)
        if frame.empty:
            return None
        last = frame.iloc[-1]
        timestamp = last["timestamp"]
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        return {"series_id": series_id, "timestamp": timestamp, "value": float(last["value"])}

