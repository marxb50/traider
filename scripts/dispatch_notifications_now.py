from __future__ import annotations

import argparse
import socket
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.services.notification_service import drain_pending_notifications
from scripts.receipt_utils import write_json_receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Despacha/drena notificações pendentes da outbox do SUPER_TRADER_QUANT.")
    parser.add_argument("--run-id", help="Identificador opcional da rodada operacional.")
    parser.add_argument("--kind", help="Filtra por kind.")
    parser.add_argument("--dedupe-key-prefix", help="Filtra por prefixo da dedupe_key.")
    parser.add_argument("--limit", type=int, help="Tamanho máximo de cada lote.")
    parser.add_argument("--max-batches", type=int, default=10, help="Número máximo de lotes a tentar.")
    parser.add_argument("--require-empty", action="store_true", help="Falha se ainda restarem notificações pendentes ao final.")
    parser.add_argument("--output", help="Salva o relatório JSON completo.")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        report = drain_pending_notifications(
            session,
            limit=args.limit,
            max_batches=args.max_batches,
            kind=args.kind,
            dedupe_key_prefix=args.dedupe_key_prefix,
        )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["hostname"] = socket.gethostname()
    report["app_env"] = settings.app_env
    if args.run_id:
        report["run_id"] = args.run_id

    if args.output:
        write_json_receipt(Path(args.output), report)

    for key, value in report.items():
        print(f"{key}: {value}")

    if args.require_empty:
        raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
