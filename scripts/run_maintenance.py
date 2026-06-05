from __future__ import annotations

import argparse

from sqlmodel import Session

from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.services.maintenance_service import run_operational_maintenance


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa manutenção operacional segura do SUPER_TRADER_QUANT.")
    parser.add_argument("--no-backup", action="store_true", help="Não cria backup antes da limpeza.")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        report = run_operational_maintenance(session, create_backup=not args.no_backup)

    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
