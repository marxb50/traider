from __future__ import annotations

from sqlmodel import Session, select

from ..config import settings
from ..models.notification import Notification
from ..time_utils import utc_now_naive
from .notification_service import dispatch_pending_notifications, enqueue_notification
from .telegram_service import PRIMARY_ROUTE, get_telegram_route_chat_ids


def enqueue_and_dispatch_telegram_canary(
    session: Session,
    *,
    route: str = PRIMARY_ROUTE,
) -> dict[str, object]:
    """Exercise the same durable outbox path used by scanner signal alerts."""

    expected_recipients = get_telegram_route_chat_ids(route)
    if not expected_recipients:
        raise RuntimeError(f"Destinatários Telegram não configurados para a rota {route}.")

    timestamp = utc_now_naive().strftime("%Y%m%d-%H%M%S-%f")
    base_key = f"telegram_canary:{route}:{timestamp}"
    message = (
        "[SUPER_TRADER_QUANT] CANARIO Telegram via outbox - "
        "pipeline de alertas simulados funcionando. SIMULACAO - NAO E CONTA REAL"
    )
    created = enqueue_notification(
        session,
        kind="telegram_canary",
        dedupe_key=base_key,
        message=message,
        routes=[route],
    )
    session.commit()
    sent = dispatch_pending_notifications(
        session,
        limit=max(len(created), 1),
        kind="telegram_canary",
        dedupe_key_prefix=base_key,
    )
    notifications = session.exec(
        select(Notification).where(Notification.kind == "telegram_canary", Notification.dedupe_key.startswith(base_key))
    ).all()
    pending = [notification for notification in notifications if notification.status == "pending"]
    failed = [notification for notification in notifications if notification.status == "failed"]
    return {
        "generated_at": utc_now_naive().isoformat(),
        "route": route,
        "base_key": base_key,
        "created": len(created),
        "sent": len(sent),
        "pending": len(pending),
        "failed": len(failed),
        "expected_recipients": expected_recipients,
        "sent_chat_ids": sorted(notification.chat_id for notification in sent if notification.chat_id),
        "ok": len(sent) == len(expected_recipients) and not pending and not failed,
    }
