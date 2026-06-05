import logging

from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.database import init_db
from super_trader_quant.backend.app.logging_config import configure_logging
from super_trader_quant.backend.app.services.process_lock import AlreadyRunningError, ProcessLock
from super_trader_quant.backend.app.services.scheduler_service import build_scheduler, run_startup_cycle

logger = logging.getLogger(__name__)


def main():
    configure_logging("scheduler")
    init_db()
    try:
        with ProcessLock(settings.resolved_scheduler_lock_path):
            logger.info("Trava exclusiva do scheduler obtida: %s", settings.resolved_scheduler_lock_path)
            run_startup_cycle()
            scheduler = build_scheduler()
            scheduler.start()
    except AlreadyRunningError as exc:
        logger.error("%s", exc)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
