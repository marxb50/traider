import pytest

from super_trader_quant.backend.app.data_providers.brapi_provider import (
    BrapiProvider,
    brapi_can_fetch_without_token,
    normalize_brapi_symbol,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_brapi_provider_parses_historical_prices(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "results": [
                    {
                        "historicalDataPrice": [
                            {
                                "date": 1756126800,
                                "open": 30.47,
                                "high": 30.78,
                                "low": 30.42,
                                "close": 30.65,
                                "volume": 21075300,
                            }
                        ]
                    }
                ]
            }
        )

    monkeypatch.setattr("super_trader_quant.backend.app.data_providers.brapi_provider.requests.get", fake_get)
    monkeypatch.setattr("super_trader_quant.backend.app.data_providers.brapi_provider.settings.brapi_token", "token-123")

    frame = BrapiProvider().fetch_history("PETR4.SA", timeframe="D1", period="5d")

    assert captured["url"].endswith("/quote/PETR4")
    assert captured["params"] == {"range": "5d", "interval": "1d"}
    assert captured["headers"] == {"Authorization": "Bearer token-123"}
    assert captured["timeout"] == 20
    assert frame.iloc[0]["close"] == 30.65
    assert frame.attrs["source_audit"]["provider"] == "brapi"


def test_brapi_requires_token_for_non_public_ticker(monkeypatch):
    monkeypatch.setattr("super_trader_quant.backend.app.data_providers.brapi_provider.settings.brapi_token", "")

    with pytest.raises(ValueError, match="BRAPI_TOKEN"):
        BrapiProvider().fetch_history("WEGE3.SA")


def test_brapi_symbol_helpers():
    assert normalize_brapi_symbol("petr4.sa") == "PETR4"
    assert brapi_can_fetch_without_token("VALE3.SA") is True
    assert brapi_can_fetch_without_token("WEGE3.SA") is False

