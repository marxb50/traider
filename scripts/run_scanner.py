import argparse
from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import init_db
from super_trader_quant.backend.app.services.operational_cycle_service import run_signal_cycle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="simulated")
    parser.add_argument("--timeframe", default=settings.scan_timeframe)
    parser.add_argument("--symbol", action="append", dest="symbols", help="Opcional: limitar a um ou mais símbolos.")
    parser.add_argument("--no-lock", action="store_true", help="Não usa a trava do scheduler.")
    args = parser.parse_args()
    init_db()
    report = run_signal_cycle(
        provider_name=args.provider,
        timeframe=args.timeframe,
        symbols=args.symbols,
        use_lock=not args.no_lock,
    )
    if report.get("skipped"):
        print(f"ciclo ignorado: {report['reason']}")
        raise SystemExit(2)
    print(
        f"novos sinais: {report['created_signals']} | "
        f"sinais resolvidos: {report['resolved_signals']} | "
        f"notificações enviadas: {report['sent_notifications']}"
    )


if __name__ == "__main__":
    main()
