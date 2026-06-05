from datetime import datetime, timedelta

from sqlmodel import Session, select

from ..config import settings
from ..models.notification import Notification
from ..time_utils import utc_now_naive
from .telegram_service import (
    BRAZIL_ROUTE,
    PRIMARY_ROUTE,
    get_telegram_route_chat_ids,
    get_telegram_route_token,
    is_telegram_route_partially_configured,
    send_telegram_message,
)


def _pending_notifications_statement(
    *,
    kind: str | None = None,
    dedupe_key_prefix: str | None = None,
):
    statement = select(Notification).where(Notification.status == "pending")
    if kind is not None:
        statement = statement.where(Notification.kind == kind)
    if dedupe_key_prefix is not None:
        statement = statement.where(Notification.dedupe_key.startswith(dedupe_key_prefix))
    return statement


def _resolve_notification_routes(
    *,
    market: str | None = None,
    routes: list[str] | None = None,
) -> list[str]:
    if routes is not None:
        return list(dict.fromkeys(routes))

    resolved_routes = []
    if is_telegram_route_partially_configured(PRIMARY_ROUTE):
        resolved_routes.append(PRIMARY_ROUTE)
    if market and market.upper() == "BR" and is_telegram_route_partially_configured(BRAZIL_ROUTE):
        resolved_routes.append(BRAZIL_ROUTE)
    return resolved_routes


def _notification_dedupe_key(base_key: str, route: str, chat_id: str | None) -> str:
    if chat_id is None:
        return f"{base_key}:{route}"
    return f"{base_key}:{route}:{chat_id}"


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    for route in (PRIMARY_ROUTE, BRAZIL_ROUTE):
        token = get_telegram_route_token(route)
        if token:
            message = message.replace(token, "<telegram-token>")
    return message


def enqueue_notification(
    session: Session,
    *,
    kind: str,
    dedupe_key: str,
    message: str,
    market: str | None = None,
    routes: list[str] | None = None,
) -> list[Notification]:
    notifications: list[Notification] = []
    for route in _resolve_notification_routes(market=market, routes=routes):
        recipients = get_telegram_route_chat_ids(route) or [None]
        for chat_id in recipients:
            recipient_key = _notification_dedupe_key(dedupe_key, route, chat_id)
            existing = session.exec(
                select(Notification).where(Notification.dedupe_key == recipient_key)
            ).first()
            if existing:
                notifications.append(existing)
                continue
            notification = Notification(
                kind=kind,
                route=route,
                dedupe_key=recipient_key,
                chat_id=chat_id,
                message=message,
            )
            session.add(notification)
            notifications.append(notification)
    return notifications


def dispatch_pending_notifications(
    session: Session,
    limit: int | None = None,
    *,
    kind: str | None = None,
    dedupe_key_prefix: str | None = None,
) -> list[Notification]:
    batch_limit = limit if limit is not None else settings.notification_batch_size
    statement = _pending_notifications_statement(kind=kind, dedupe_key_prefix=dedupe_key_prefix).order_by(
        Notification.created_at
    ).limit(batch_limit)
    notifications = session.exec(statement).all()
    sent: list[Notification] = []
    for notification in notifications:
        route = notification.route or PRIMARY_ROUTE
        route_token = get_telegram_route_token(route)
        route_chat_ids = get_telegram_route_chat_ids(route)
        try:
            if not route_token:
                notification.last_error = f"telegram_not_configured:{route}"
                session.add(notification)
                continue
            if notification.chat_id is None and not route_chat_ids:
                notification.last_error = f"telegram_no_recipients:{route}"
                session.add(notification)
                continue
            delivered_to = send_telegram_message(
                notification.message,
                chat_ids=[notification.chat_id] if notification.chat_id else None,
                route=route,
            )
            if not delivered_to:
                notification.last_error = f"telegram_no_delivery:{route}"
                session.add(notification)
                continue
            notification.status = "sent"
            notification.attempts += 1
            notification.sent_at = utc_now_naive()
            notification.last_error = None
            session.add(notification)
            sent.append(notification)
        except Exception as exc:  # noqa: BLE001
            notification.attempts += 1
            notification.last_error = _safe_error_message(exc)
            if notification.attempts >= settings.notification_max_attempts:
                notification.status = "failed"
            session.add(notification)
    session.commit()
    return sent


def count_pending_notifications(
    session: Session,
    *,
    kind: str | None = None,
    dedupe_key_prefix: str | None = None,
) -> int:
    statement = _pending_notifications_statement(kind=kind, dedupe_key_prefix=dedupe_key_prefix)
    return len(session.exec(statement).all())


def drain_pending_notifications(
    session: Session,
    *,
    limit: int | None = None,
    max_batches: int = 10,
    kind: str | None = None,
    dedupe_key_prefix: str | None = None,
) -> dict[str, object]:
    if max_batches <= 0:
        raise ValueError("max_batches deve ser maior que zero")

    batch_limit = limit if limit is not None else settings.notification_batch_size
    total_sent = 0
    total_failed = 0
    batches: list[dict[str, object]] = []
    pending_before_start = count_pending_notifications(
        session,
        kind=kind,
        dedupe_key_prefix=dedupe_key_prefix,
    )
    pending_after_end = pending_before_start
    stop_reason = "queue_empty" if pending_before_start == 0 else "max_batches_reached"

    for batch_index in range(1, max_batches + 1):
        pending_before = count_pending_notifications(
            session,
            kind=kind,
            dedupe_key_prefix=dedupe_key_prefix,
        )
        if pending_before == 0:
            pending_after_end = 0
            stop_reason = "queue_empty"
            break

        selected = session.exec(
            _pending_notifications_statement(kind=kind, dedupe_key_prefix=dedupe_key_prefix)
            .order_by(Notification.created_at)
            .limit(batch_limit)
        ).all()
        selected_ids = [notification.id for notification in selected]
        before_snapshot = {
            notification.id: {
                "status": notification.status,
                "attempts": notification.attempts,
                "last_error": notification.last_error,
            }
            for notification in selected
        }

        sent = dispatch_pending_notifications(
            session,
            limit=batch_limit,
            kind=kind,
            dedupe_key_prefix=dedupe_key_prefix,
        )
        total_sent += len(sent)
        session.expire_all()

        progressed = False
        failed_in_batch = 0
        last_errors: list[str] = []
        for notification_id in selected_ids:
            current = session.get(Notification, notification_id)
            if current is None:
                continue
            previous = before_snapshot[notification_id]
            if (
                current.status != previous["status"]
                or current.attempts != previous["attempts"]
            ):
                progressed = True
            if previous["status"] != "failed" and current.status == "failed":
                failed_in_batch += 1
            if current.last_error:
                last_errors.append(current.last_error)

        total_failed += failed_in_batch
        pending_after = count_pending_notifications(
            session,
            kind=kind,
            dedupe_key_prefix=dedupe_key_prefix,
        )
        if pending_after < pending_before:
            progressed = True

        batch_report = {
            "batch": batch_index,
            "pending_before": pending_before,
            "pending_after": pending_after,
            "sent": len(sent),
            "failed": failed_in_batch,
            "progressed": progressed,
            "last_errors": sorted(set(last_errors)),
        }
        batches.append(batch_report)
        pending_after_end = pending_after

        if pending_after == 0:
            stop_reason = "queue_empty"
            break
        if not progressed:
            stop_reason = "stalled"
            break
    else:
        pending_after_end = count_pending_notifications(
            session,
            kind=kind,
            dedupe_key_prefix=dedupe_key_prefix,
        )
        stop_reason = "max_batches_reached"

    return {
        "ok": pending_after_end == 0,
        "kind": kind,
        "dedupe_key_prefix": dedupe_key_prefix,
        "limit": batch_limit,
        "max_batches": max_batches,
        "pending_before": pending_before_start,
        "pending_after": pending_after_end,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "processed_batches": len(batches),
        "stop_reason": stop_reason,
        "batches": batches,
    }


def suppress_pending_notifications(
    session: Session,
    *,
    older_than_minutes: int | None = None,
    before: datetime | None = None,
    kind: str | None = None,
    dedupe_key_prefix: str | None = None,
    reason: str = "suppressed_before_live_cutover",
    dry_run: bool = False,
) -> dict[str, object]:
    if older_than_minutes is not None and older_than_minutes < 0:
        raise ValueError("older_than_minutes deve ser maior ou igual a zero")
    if older_than_minutes is None and before is None:
        raise ValueError("Informe older_than_minutes ou before para suprimir pendências")

    cutoff = before
    if cutoff is None:
        cutoff = utc_now_naive() - timedelta(minutes=older_than_minutes or 0)

    statement = _pending_notifications_statement(kind=kind, dedupe_key_prefix=dedupe_key_prefix).where(
        Notification.created_at < cutoff
    )
    notifications = session.exec(statement.order_by(Notification.created_at)).all()
    report = {
        "ok": True,
        "kind": kind,
        "dedupe_key_prefix": dedupe_key_prefix,
        "reason": reason,
        "dry_run": dry_run,
        "older_than_minutes": older_than_minutes,
        "before": cutoff.isoformat(),
        "suppressed_count": len(notifications),
        "suppressed_ids": [notification.id for notification in notifications],
        "oldest_created_at": notifications[0].created_at.isoformat() if notifications else None,
        "newest_created_at": notifications[-1].created_at.isoformat() if notifications else None,
    }
    if dry_run or not notifications:
        return report

    for notification in notifications:
        notification.status = "suppressed"
        notification.last_error = reason
        session.add(notification)
    session.commit()
    return report
