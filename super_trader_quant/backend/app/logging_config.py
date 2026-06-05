import logging
from logging.handlers import RotatingFileHandler
from .config import settings


def configure_logging(process_name: str) -> None:
    log_file = settings.resolved_log_dir / f"{process_name}.log"
    root_logger = logging.getLogger()
    if getattr(root_logger, "_super_trader_configured", False):
        return

    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger._super_trader_configured = True  # type: ignore[attr-defined]
