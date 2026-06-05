from datetime import timedelta

from sqlmodel import SQLModel, Session, create_engine, select
from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.services import notification_service


def test_notification_outbox_deduplicates_and_dispatches(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": sent_messages.append((message, chat_ids, route)) or ["111111111"],
    )

    with Session(engine) as session:
        notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:abc",
            message="mensagem 1",
        )
        notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:abc",
            message="mensagem duplicada",
        )
        session.commit()

        sent = notification_service.dispatch_pending_notifications(session)
        notifications = session.exec(select(Notification)).all()

    assert len(notifications) == 1
    assert len(sent) == 1
    assert sent_messages == [("mensagem 1", ["111111111"], "primary")]
    assert notifications[0].status == "sent"
    assert notifications[0].route == "primary"


def test_notification_outbox_marks_failed_after_max_attempts(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(notification_service.settings, "notification_max_attempts", 2)
    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": (_ for _ in ()).throw(RuntimeError("telegram down")),
    )

    with Session(engine) as session:
        notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:def",
            message="mensagem 2",
        )
        session.commit()

        notification_service.dispatch_pending_notifications(session)
        notification_service.dispatch_pending_notifications(session)
        notification = session.exec(select(Notification)).one()

    assert notification.attempts == 2
    assert notification.status == "failed"
    assert "telegram down" in (notification.last_error or "")


def test_notification_outbox_keeps_pending_when_token_missing(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")

    with Session(engine) as session:
        notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:no-token",
            message="mensagem sem token",
        )
        session.commit()
        notification_service.dispatch_pending_notifications(session)
        notification = session.exec(select(Notification)).one()

    assert notification.status == "pending"
    assert notification.attempts == 0
    assert notification.last_error == "telegram_not_configured:primary"


def test_notification_outbox_fans_out_per_recipient(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "1,2")

    def fake_send(message, chat_ids=None, route="primary"):
        if chat_ids == ["2"]:
            raise RuntimeError("chat inválido")
        return chat_ids or []

    monkeypatch.setattr(notification_service, "send_telegram_message", fake_send)

    with Session(engine) as session:
        created = notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:fanout",
            message="mensagem fanout",
        )
        session.commit()
        notification_service.dispatch_pending_notifications(session)
        notifications = sorted(
            session.exec(select(Notification)).all(),
            key=lambda item: item.chat_id or "",
        )

    assert len(created) == 2
    assert [notification.chat_id for notification in notifications] == ["1", "2"]
    assert notifications[0].status == "sent"
    assert notifications[1].status == "pending"
    assert notifications[1].attempts == 1


def test_notification_dispatch_respects_explicit_limit(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": sent_messages.append((message, route)) or ["111111111"],
    )

    with Session(engine) as session:
        for index in range(3):
            notification_service.enqueue_notification(
                session,
                kind="signal_opened",
                dedupe_key=f"signal_opened:limit:{index}",
                message=f"mensagem {index}",
            )
        session.commit()

        sent = notification_service.dispatch_pending_notifications(session, limit=2)
        pending = session.exec(select(Notification).where(Notification.status == "pending")).all()

    assert len(sent) == 2
    assert len(sent_messages) == 2
    assert all(route == "primary" for _, route in sent_messages)
    assert len(pending) == 1


def test_notification_dispatch_can_filter_by_kind_and_dedupe_prefix(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": sent_messages.append((message, route)) or ["111111111"],
    )

    with Session(engine) as session:
        notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:old",
            message="não enviar agora",
        )
        notification_service.enqueue_notification(
            session,
            kind="telegram_canary",
            dedupe_key="telegram_canary:abc",
            message="enviar canário",
        )
        session.commit()

        sent = notification_service.dispatch_pending_notifications(
            session,
            kind="telegram_canary",
            dedupe_key_prefix="telegram_canary:abc",
        )
        notifications = session.exec(select(Notification)).all()

    assert len(sent) == 1
    assert sent_messages == [("enviar canário", "primary")]
    statuses = {notification.message: notification.status for notification in notifications}
    assert statuses["enviar canário"] == "sent"
    assert statuses["não enviar agora"] == "pending"


def test_notification_drain_pending_notifications_until_empty(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")
    monkeypatch.setattr(notification_service.settings, "notification_batch_size", 2)
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": sent_messages.append((message, route)) or ["111111111"],
    )

    with Session(engine) as session:
        for index in range(3):
            notification_service.enqueue_notification(
                session,
                kind="signal_opened",
                dedupe_key=f"signal_opened:drain:{index}",
                message=f"mensagem drain {index}",
            )
        session.commit()

        report = notification_service.drain_pending_notifications(session, limit=2, max_batches=5)
        remaining = session.exec(select(Notification).where(Notification.status == "pending")).all()

    assert report["ok"] is True
    assert report["pending_before"] == 3
    assert report["pending_after"] == 0
    assert report["total_sent"] == 3
    assert report["processed_batches"] == 2
    assert report["stop_reason"] == "queue_empty"
    assert len(remaining) == 0
    assert len(sent_messages) == 3
    assert all(route == "primary" for _, route in sent_messages)


def test_notification_drain_detects_stalled_queue_when_token_missing(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "111111111")

    with Session(engine) as session:
        notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:stalled",
            message="mensagem stalled",
        )
        session.commit()

        report = notification_service.drain_pending_notifications(session, max_batches=3)
        notification = session.exec(select(Notification)).one()

    assert report["ok"] is False
    assert report["pending_before"] == 1
    assert report["pending_after"] == 1
    assert report["processed_batches"] == 1
    assert report["stop_reason"] == "stalled"
    assert notification.status == "pending"
    assert notification.last_error == "telegram_not_configured:primary"


def test_notification_suppression_marks_only_old_pending(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    now = notification_service.utc_now_naive()
    monkeypatch.setattr(notification_service, "utc_now_naive", lambda: now)

    with Session(engine) as session:
        old_notification = Notification(
            dedupe_key="signal_opened:old",
            kind="signal_opened",
            message="antiga",
            created_at=now - timedelta(minutes=10),
        )
        fresh_notification = Notification(
            dedupe_key="signal_opened:fresh",
            kind="signal_opened",
            message="nova",
            created_at=now,
        )
        session.add(old_notification)
        session.add(fresh_notification)
        session.commit()

        report = notification_service.suppress_pending_notifications(
            session,
            older_than_minutes=5,
            reason="suppressed_before_live_cutover",
        )
        notifications = {
            notification.dedupe_key: notification
            for notification in session.exec(select(Notification)).all()
        }

    assert report["suppressed_count"] == 1
    assert notifications["signal_opened:old"].status == "suppressed"
    assert notifications["signal_opened:old"].last_error == "suppressed_before_live_cutover"
    assert notifications["signal_opened:fresh"].status == "pending"


def test_notification_suppression_dry_run_keeps_pending():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    now = notification_service.utc_now_naive()

    with Session(engine) as session:
        notification = Notification(
            dedupe_key="signal_opened:dry",
            kind="signal_opened",
            message="dry",
            created_at=now - timedelta(minutes=10),
        )
        session.add(notification)
        session.commit()

        report = notification_service.suppress_pending_notifications(
            session,
            older_than_minutes=5,
            dry_run=True,
        )
        refreshed = session.exec(select(Notification)).one()

    assert report["suppressed_count"] == 1
    assert refreshed.status == "pending"


def test_notification_br_market_fans_out_to_primary_and_br_routes(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "1")
    monkeypatch.setattr(notification_service.settings, "telegram_br_bot_token", "br-token-456")
    monkeypatch.setattr(notification_service.settings, "telegram_br_chat_ids", "2")

    def fake_send(message, chat_ids=None, route="primary"):
        sent_messages.append((message, chat_ids, route))
        return chat_ids or []

    monkeypatch.setattr(notification_service, "send_telegram_message", fake_send)

    with Session(engine) as session:
        created = notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:br-market",
            message="mensagem br",
            market="BR",
        )
        session.commit()
        sent = notification_service.dispatch_pending_notifications(session)
        notifications = sorted(
            session.exec(select(Notification)).all(),
            key=lambda item: (item.route, item.chat_id or ""),
        )

    assert len(created) == 2
    assert len(sent) == 2
    assert [(notification.route, notification.chat_id) for notification in notifications] == [
        ("br", "2"),
        ("primary", "1"),
    ]
    assert [item[2] for item in sent_messages] == ["primary", "br"]


def test_notification_br_only_route_does_not_enqueue_primary_when_paused(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "")
    monkeypatch.setattr(notification_service.settings, "telegram_br_bot_token", "br-token-456")
    monkeypatch.setattr(notification_service.settings, "telegram_br_chat_ids", "2")

    with Session(engine) as session:
        created = notification_service.enqueue_notification(
            session,
            kind="signal_opened",
            dedupe_key="signal_opened:br-only",
            message="mensagem br only",
            market="BR",
        )
        session.commit()
        notifications = session.exec(select(Notification)).all()

    assert len(created) == 1
    assert [(notification.route, notification.chat_id) for notification in notifications] == [("br", "2")]
