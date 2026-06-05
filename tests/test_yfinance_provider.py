import pandas as pd

from super_trader_quant.backend.app.data_providers.yfinance_provider import YFinanceProvider


def test_yfinance_provider_redirects_cache_under_project_data(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.settings.scheduler_lock_path",
        str(tmp_path / "scheduler.lock"),
    )
    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.yf.set_tz_cache_location",
        lambda path: captured.setdefault("path", path),
    )

    YFinanceProvider()

    assert captured["path"] == str(tmp_path / "cache" / "py-yfinance")
    assert (tmp_path / "cache" / "py-yfinance").exists()


def test_yfinance_provider_fetch_many_disables_download_threads(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.settings.scheduler_lock_path",
        str(tmp_path / "scheduler.lock"),
    )
    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.yf.set_tz_cache_location",
        lambda path: None,
    )

    def fake_download(symbols, **kwargs):
        calls["symbols"] = symbols
        calls["kwargs"] = kwargs
        return pd.DataFrame()

    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.yf.download",
        fake_download,
    )

    provider = YFinanceProvider()
    result = provider.fetch_many_history(["AAPL"])

    assert calls["kwargs"]["threads"] is False
    assert "AAPL" in result


def test_yfinance_provider_maps_h1_to_60m_interval(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.settings.scheduler_lock_path",
        str(tmp_path / "scheduler.lock"),
    )
    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.yf.set_tz_cache_location",
        lambda path: None,
    )

    def fake_download(symbols, **kwargs):
        calls["kwargs"] = kwargs
        return pd.DataFrame()

    monkeypatch.setattr(
        "super_trader_quant.backend.app.data_providers.yfinance_provider.yf.download",
        fake_download,
    )

    provider = YFinanceProvider()
    provider.fetch_many_history(["AAPL"], timeframe="H1", period="3mo")

    assert calls["kwargs"]["interval"] == "60m"
    assert calls["kwargs"]["period"] == "3mo"
