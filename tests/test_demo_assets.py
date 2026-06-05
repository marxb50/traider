from super_trader_quant.backend.app.demo_assets import (
    BRAZIL_ASSETS,
    EXPECTED_ASSET_COUNT,
    EXPECTED_ASSETS_BY_MARKET,
    US_ASSETS,
    UK_ASSETS,
)


def test_demo_asset_counts():
    assert len(BRAZIL_ASSETS) == 100
    assert len(US_ASSETS) == 50
    assert len(UK_ASSETS) == 50
    assert EXPECTED_ASSETS_BY_MARKET == {"BR": 100, "US": 50, "UK": 50}
    assert EXPECTED_ASSET_COUNT == 200
