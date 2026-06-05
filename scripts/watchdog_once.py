from __future__ import annotations

import argparse

from sqlmodel import Session

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.services.notification_service import dispatch_pending_notifications
from super_trader_quant.backend.app.services.watchdog_service import (
    collect_watchdog_report,
    enqueue_watchdog_notification,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa uma checagem operacional do SUPER_TRADER_QUANT.")
    parser.add_argument("--strict", action="store_true", help="Exige token Telegram e provider não simulado.")
    parser.add_argument("--notify-ok", action="store_true", help="Também envia alerta Telegram quando tudo está OK.")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        report = collect_watchdog_report(session, strict=args.strict)
        queued = enqueue_watchdog_notification(session, report, notify_ok=args.notify_ok)
        session.commit()
        sent = dispatch_pending_notifications(session, limit=settings.immediate_notification_batch_size)

    print(f"ok: {report['ok']}")
    print(f"strict: {report['strict']}")
    print(f"issues: {report['issues']}")
    print(f"queued_notifications: {len(queued)}")
    print(f"sent_notifications: {len(sent)}")
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
