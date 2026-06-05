from datetime import datetime

from super_trader_quant.backend.app.data_providers.bcb_provider import BCBSgsProvider


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return [
            {"data": "01/06/2026", "valor": "10,50"},
            {"data": "02/06/2026", "valor": "10.75"},
        ]


def test_bcb_sgs_provider_parses_series(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("super_trader_quant.backend.app.data_providers.bcb_provider.requests.get", fake_get)

    frame = BCBSgsProvider().fetch_series(432, start=datetime(2026, 6, 1), end="02/06/2026")

    assert captured["url"].endswith(".432/dados")
    assert captured["params"] == {
        "formato": "json",
        "dataInicial": "01/06/2026",
        "dataFinal": "02/06/2026",
    }
    assert captured["timeout"] == 20
    assert frame.iloc[0]["value"] == 10.5
    assert frame.iloc[-1]["value"] == 10.75

