import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlmodel import Session
from ..config import settings
from ..database import engine
from ..data_providers.factory import get_provider
from ..engine.scanner_engine import resolve_open_signals, scan_assets
from .heartbeat_service import update_scheduler_heartbeat
from .maintenance_service import run_operational_maintenance
from .notification_service import dispatch_pending_notifications

logger = logging.getLogger(__name__)


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 300,
        },
    )
    provider = get_provider(settings.default_provider)

    def scan_job():
        with Session(engine) as session:
            created = scan_assets(session, provider, timeframe=settings.scan_timeframe)
            logger.info("Scanner concluído: %s novos sinais", len(created))
            sent = dispatch_pending_notifications(session, limit=settings.immediate_notification_batch_size)
            logger.info("Notificações pós-scan despachadas imediatamente: %s", len(sent))
            update_scheduler_heartbeat(
                "scan_job",
                {
                    "last_scan_created": len(created),
                    "last_scan_timeframe": settings.scan_timeframe,
                    "last_scan_notifications_sent": len(sent),
                },
            )

    def resolve_job():
        with Session(engine) as session:
            resolved = resolve_open_signals(session, provider)
            logger.info("Resolução concluída: %s sinais encerrados", len(resolved))
            sent = dispatch_pending_notifications(session, limit=settings.immediate_notification_batch_size)
            logger.info("Notificações pós-resolução despachadas imediatamente: %s", len(sent))
            update_scheduler_heartbeat(
                "resolve_job",
                {
                    "last_resolved_count": len(resolved),
                    "last_resolve_notifications_sent": len(sent),
                },
            )

    def notification_job():
        with Session(engine) as session:
            sent = dispatch_pending_notifications(session)
            logger.info("Despacho de notificações concluído: %s enviadas", len(sent))
            update_scheduler_heartbeat("notification_job", {"last_notifications_sent": len(sent)})

    def maintenance_job():
        with Session(engine) as session:
            report = run_operational_maintenance(session)
            logger.info("Manutenção operacional concluída: %s", report)
            update_scheduler_heartbeat(
                "maintenance_job",
                {
                    "last_maintenance_deleted_sent": report["deleted_sent_notifications"],
                    "last_maintenance_deleted_failed": report["deleted_failed_notifications"],
                    "last_maintenance_backup_path": report["backup_path"],
                    "last_maintenance_backup_error": report["backup_error"],
                    "last_maintenance_deleted_backups": len(report["backup_prune_report"]["deleted_backups"]),
                },
            )

    scheduler.add_job(scan_job, "interval", minutes=settings.scan_interval_minutes, id="scan_job", replace_existing=True)
    scheduler.add_job(resolve_job, "interval", minutes=settings.outcome_check_interval_minutes, id="resolve_job", replace_existing=True)
    scheduler.add_job(
        notification_job,
        "interval",
        minutes=settings.notification_dispatch_interval_minutes,
        id="notification_job",
        replace_existing=True,
    )
    scheduler.add_job(
        maintenance_job,
        "interval",
        minutes=settings.maintenance_interval_minutes,
        id="maintenance_job",
        replace_existing=True,
    )
    return scheduler


def run_startup_cycle() -> None:
    provider = get_provider(settings.default_provider)
    update_scheduler_heartbeat("startup_begin")
    with Session(engine) as session:
        created = scan_assets(session, provider, timeframe=settings.scan_timeframe)
        logger.info("Startup scanner concluído: %s novos sinais", len(created))
        update_scheduler_heartbeat(
            "startup_scan",
            {
                "startup_created": len(created),
                "startup_scan_timeframe": settings.scan_timeframe,
            },
        )
    with Session(engine) as session:
        resolved = resolve_open_signals(session, provider)
        logger.info("Startup resolução concluída: %s sinais encerrados", len(resolved))
        update_scheduler_heartbeat("startup_resolve", {"startup_resolved": len(resolved)})
    with Session(engine) as session:
        sent = dispatch_pending_notifications(session)
        logger.info("Startup notificações concluídas: %s enviadas", len(sent))
        update_scheduler_heartbeat("startup_notifications", {"startup_notifications_sent": len(sent)})
    with Session(engine) as session:
        report = run_operational_maintenance(session)
        logger.info("Startup manutenção concluída: %s", report)
        update_scheduler_heartbeat(
            "startup_maintenance",
            {
                "startup_maintenance_deleted_sent": report["deleted_sent_notifications"],
                "startup_maintenance_deleted_failed": report["deleted_failed_notifications"],
                "startup_maintenance_backup_path": report["backup_path"],
                "startup_maintenance_backup_error": report["backup_error"],
                "startup_maintenance_deleted_backups": len(report["backup_prune_report"]["deleted_backups"]),
            },
        )
