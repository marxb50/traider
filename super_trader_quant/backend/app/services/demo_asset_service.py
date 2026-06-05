from sqlmodel import Session, select
from ..demo_assets import DEMO_ASSETS_BY_MARKET
from ..models.asset import Asset

COUNTRY_MAP = {"BR": "Brasil", "US": "EUA", "UK": "Reino Unido"}


def sync_demo_assets(session: Session) -> dict[str, int]:
    desired_by_symbol = {
        symbol: (market, COUNTRY_MAP[market])
        for market, symbols in DEMO_ASSETS_BY_MARKET.items()
        for symbol in symbols
    }
    existing_assets = session.exec(select(Asset)).all()
    existing_by_symbol = {asset.symbol: asset for asset in existing_assets}

    created = 0
    reactivated = 0
    deactivated = 0
    updated = 0

    for symbol, (market, country) in desired_by_symbol.items():
        asset = existing_by_symbol.get(symbol)
        if asset is None:
            session.add(Asset(symbol=symbol, market=market, country=country, active=True))
            created += 1
            continue
        changed = False
        if asset.market != market:
            asset.market = market
            changed = True
        if asset.country != country:
            asset.country = country
            changed = True
        if not asset.active:
            asset.active = True
            reactivated += 1
            changed = True
        if changed:
            session.add(asset)
            updated += 1

    desired_symbols = set(desired_by_symbol)
    managed_markets = set(DEMO_ASSETS_BY_MARKET)
    for asset in existing_assets:
        if asset.market in managed_markets and asset.symbol not in desired_symbols and asset.active:
            asset.active = False
            session.add(asset)
            deactivated += 1

    session.commit()
    return {
        "created": created,
        "reactivated": reactivated,
        "deactivated": deactivated,
        "updated": updated,
    }
