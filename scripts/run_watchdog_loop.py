from __future__ import annotations

import logging
import time

from sqlmodel import Session

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.logging_config import configure_logging
from super_trader_quant.backend.app.services.notification_service import dispatch_pending_notifications
from super_trader_quant.backend.app.services.watchdog_service import (
    collect_watchdog_report,
    enqueue_watchdog_notification,
)

logger = logging.getLogger(__name__)


def run_once() -> dict[str, object]:
    with Session(engine) as session:
        report = collect_watchdog_report(session, strict=True)
        queued = enqueue_watchdog_notification(session, report)
        session.commit()
        sent = dispatch_pending_notifications(session, limit=settings.immediate_notification_batch_size)
    logger.info(
        "Watchdog concluído: ok=%s issues=%s queued=%s sent=%s",
        report["ok"],
        len(report["issues"]),
        len(queued),
        len(sent),
    )
    return report


def main() -> None:
    configure_logging("watchdog")
    init_db()
    interval_seconds = max(settings.watchdog_interval_minutes, 1) * 60
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Falha no loop do watchdog")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
