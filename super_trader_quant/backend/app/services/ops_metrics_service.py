from collections import Counter
from sqlmodel import Session, select
from ..config import settings
from ..models.asset import Asset
from ..models.notification import Notification
from ..models.signal import Signal
from ..time_utils import utc_now_naive
from .resource_guard_service import collect_resource_metrics


def collect_ops_metrics(session: Session) -> dict[str, object]:
    now = utc_now_naive()
    active_assets = session.exec(select(Asset).where(Asset.active == True)).all()  # noqa: E712
    open_signals = session.exec(select(Signal).where(Signal.status == "open")).all()
    notifications = session.exec(select(Notification)).all()
    pending_notifications = [
        notification for notification in notifications if notification.status == "pending"
    ]
    failed_notifications = [
        notification for notification in notifications if notification.status == "failed"
    ]
    suppressed_notifications = [
        notification for notification in notifications if notification.status == "suppressed"
    ]

    open_signal_ages_days = [
        (now - signal.signal_time).total_seconds() / 86400 for signal in open_signals
    ]
    pending_notification_ages_minutes = [
        (now - notification.created_at).total_seconds() / 60
        for notification in pending_notifications
    ]

    return {
        "active_assets": len(active_assets),
        "open_signals": len(open_signals),
        "open_signals_by_market": dict(Counter(signal.market for signal in open_signals)),
        "oldest_open_signal_age_days": max(open_signal_ages_days, default=0.0),
        "stale_open_signals": sum(
            age > settings.max_open_signal_age_days for age in open_signal_ages_days
        ),
        "pending_notifications": len(pending_notifications),
        "failed_notifications": len(failed_notifications),
        "suppressed_notifications": len(suppressed_notifications),
        "oldest_pending_notification_age_minutes": max(
            pending_notification_ages_minutes,
            default=0.0,
        ),
        "stale_pending_notifications": sum(
            age > settings.max_pending_notification_age_minutes
            for age in pending_notification_ages_minutes
        ),
        "resources": collect_resource_metrics(),
    }
