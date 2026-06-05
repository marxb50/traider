from __future__ import annotations

import argparse
import socket

from sqlmodel import Session

from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.services.telegram_canary_service import enqueue_and_dispatch_telegram_canary
from super_trader_quant.backend.app.services.telegram_service import PRIMARY_ROUTE, get_telegram_route_token
from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import write_json_receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispara canario Telegram via outbox e grava recibo.")
    parser.add_argument("--run-id", help="Identificador opcional da rodada de verificacao.")
    parser.add_argument("--route", default=PRIMARY_ROUTE, help="Rota Telegram: primary ou br.")
    args = parser.parse_args()
    if not get_telegram_route_token(args.route):
        raise SystemExit(f"Token Telegram nao configurado para a rota {args.route}")
    init_db()
    with Session(engine) as session:
        report = enqueue_and_dispatch_telegram_canary(session, route=args.route)
    if args.run_id:
        report["run_id"] = args.run_id
    report["hostname"] = socket.gethostname()
    report["app_env"] = settings.app_env

    receipt_name = "telegram_canary_last.json" if args.route == PRIMARY_ROUTE else f"telegram_canary_{args.route}_last.json"
    receipt_path = settings.resolved_log_dir / receipt_name
    write_json_receipt(receipt_path, report)

    for key, value in report.items():
        print(f"{key}: {value}")
    print(f"receipt: {receipt_path}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
