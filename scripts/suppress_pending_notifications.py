from __future__ import annotations

import argparse
import socket
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.services.notification_service import suppress_pending_notifications
from scripts.receipt_utils import write_json_receipt


def _parse_before(value: str | None):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suprime notificações pendentes antigas sem apagar o histórico, útil antes do primeiro go-live do Telegram."
    )
    parser.add_argument("--run-id", help="Identificador opcional da rodada operacional.")
    parser.add_argument("--kind", help="Filtra por kind.")
    parser.add_argument("--dedupe-key-prefix", help="Filtra por prefixo da dedupe_key.")
    parser.add_argument("--older-than-minutes", type=int, help="Suprime pendências mais velhas que esse valor.")
    parser.add_argument("--before", help="Suprime pendências criadas antes desse timestamp ISO.")
    parser.add_argument("--reason", default="suppressed_before_live_cutover")
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o que seria suprimido.")
    parser.add_argument("--output", help="Salva o relatório JSON completo.")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        report = suppress_pending_notifications(
            session,
            older_than_minutes=args.older_than_minutes,
            before=_parse_before(args.before),
            kind=args.kind,
            dedupe_key_prefix=args.dedupe_key_prefix,
            reason=args.reason,
            dry_run=args.dry_run,
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


if __name__ == "__main__":
    main()
