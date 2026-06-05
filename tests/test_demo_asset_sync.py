from sqlmodel import SQLModel, Session, create_engine, select
from super_trader_quant.backend.app.demo_assets import EXPECTED_ASSET_COUNT
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.services.demo_asset_service import sync_demo_assets


def test_sync_demo_assets_keeps_exact_active_universe():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Asset(symbol="OLD3.SA", market="BR", country="Brasil", active=True))
        session.commit()

        stats = sync_demo_assets(session)
        assets = session.exec(select(Asset)).all()
        active_assets = [asset for asset in assets if asset.active]

    assert stats["created"] == EXPECTED_ASSET_COUNT
    assert stats["deactivated"] == 1
    assert len(active_assets) == EXPECTED_ASSET_COUNT
    assert all(asset.symbol != "OLD3.SA" for asset in active_assets)
