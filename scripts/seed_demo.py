from sqlmodel import Session
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.services.demo_asset_service import sync_demo_assets


def main():
    init_db()
    with Session(engine) as session:
        stats = sync_demo_assets(session)
    print(f"Ativos demo sincronizados com sucesso: {stats}")


if __name__ == "__main__":
    main()
