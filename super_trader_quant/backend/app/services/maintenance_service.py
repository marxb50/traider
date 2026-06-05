from __future__ import annotations

from datetime import timedelta
from sqlmodel import Session, select

from ..config import settings
from ..models.notification import Notification
from ..time_utils import utc_now_naive
from .backup_service import BackupError, backup_sqlite_database, prune_old_backups


def run_operational_maintenance(
    session: Session,
    *,
    create_backup: bool = True,
) -> dict[str, object]:
    """Run safe retention tasks without touching trading memory or open signals."""

    backup_path = None
    backup_error = None
    if create_backup:
        try:
            backup_path = str(backup_sqlite_database(label="maintenance"))
        except BackupError as exc:
            backup_error = str(exc)

    backup_prune_report = prune_old_backups()

    now = utc_now_naive()
    sent_cutoff = now - timedelta(days=settings.sent_notification_retention_days)
    failed_cutoff = now - timedelta(days=settings.failed_notification_retention_days)

    old_sent = session.exec(
        select(Notification).where(
            Notification.status == "sent",
            Notification.sent_at != None,  # noqa: E711
            Notification.sent_at < sent_cutoff,
        )
    ).all()
    old_failed = session.exec(
        select(Notification).where(
            Notification.status == "failed",
            Notification.created_at < failed_cutoff,
        )
    ).all()
    old_suppressed = session.exec(
        select(Notification).where(
            Notification.status == "suppressed",
            Notification.created_at < failed_cutoff,
        )
    ).all()

    for notification in [*old_sent, *old_failed, *old_suppressed]:
        session.delete(notification)
    session.commit()

    return {
        "backup_path": backup_path,
        "backup_error": backup_error,
        "backup_prune_report": backup_prune_report,
        "deleted_sent_notifications": len(old_sent),
        "deleted_failed_notifications": len(old_failed),
        "deleted_suppressed_notifications": len(old_suppressed),
        "sent_retention_days": settings.sent_notification_retention_days,
        "failed_retention_days": settings.failed_notification_retention_days,
    }
