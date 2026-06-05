from __future__ import annotations

import argparse

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import init_db
from super_trader_quant.backend.app.services.operational_cycle_service import run_signal_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispara um ciclo imediato e seguro de scanner/resolução/Telegram.")
    parser.add_argument("--provider", help="Provider opcional. Padrão: DEFAULT_PROVIDER.")
    parser.add_argument("--timeframe", default=settings.scan_timeframe)
    parser.add_argument("--symbol", action="append", dest="symbols", help="Opcional: limitar a um ou mais símbolos.")
    args = parser.parse_args()

    init_db()
    report = run_signal_cycle(provider_name=args.provider, timeframe=args.timeframe, symbols=args.symbols)
    for key, value in report.items():
        print(f"{key}: {value}")
    raise SystemExit(2 if report.get("skipped") else 0)


if __name__ == "__main__":
    main()
