from sqlmodel import SQLModel, Session, create_engine, select

from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.services import notification_service, telegram_canary_service


def test_telegram_canary_uses_outbox_and_marks_all_recipients_sent(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(telegram_canary_service.settings, "telegram_chat_ids", "1,2")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "1,2")
    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": sent_messages.append((message, chat_ids, route)) or (chat_ids or []),
    )

    with Session(engine) as session:
        report = telegram_canary_service.enqueue_and_dispatch_telegram_canary(session)
        notifications = sorted(session.exec(select(Notification)).all(), key=lambda item: item.chat_id or "")

    assert report["ok"] is True
    assert "generated_at" in report
    assert report["created"] == 2
    assert report["sent"] == 2
    assert report["pending"] == 0
    assert report["failed"] == 0
    assert report["sent_chat_ids"] == ["1", "2"]
    assert [notification.status for notification in notifications] == ["sent", "sent"]
    assert [message[1] for message in sent_messages] == [["1"], ["2"]]
    assert all(message[2] == "primary" for message in sent_messages)
    assert all("CANARIO Telegram via outbox" in message[0] for message in sent_messages)


def test_telegram_canary_reports_partial_failure(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(telegram_canary_service.settings, "telegram_chat_ids", "1,2")
    monkeypatch.setattr(notification_service.settings, "telegram_chat_ids", "1,2")
    monkeypatch.setattr(notification_service.settings, "telegram_bot_token", "token-123")

    def fake_send(message, chat_ids=None, route="primary"):
        if chat_ids == ["2"]:
            raise RuntimeError("chat inválido")
        return chat_ids or []

    monkeypatch.setattr(notification_service, "send_telegram_message", fake_send)

    with Session(engine) as session:
        report = telegram_canary_service.enqueue_and_dispatch_telegram_canary(session)
        notifications = sorted(session.exec(select(Notification)).all(), key=lambda item: item.chat_id or "")

    assert report["ok"] is False
    assert "generated_at" in report
    assert report["created"] == 2
    assert report["sent"] == 1
    assert report["pending"] == 1
    assert notifications[0].status == "sent"
    assert notifications[1].status == "pending"
    assert "chat inválido" in (notifications[1].last_error or "")


def test_telegram_canary_can_target_br_route(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    sent_messages = []

    monkeypatch.setattr(telegram_canary_service.settings, "telegram_br_chat_ids", "9")
    monkeypatch.setattr(notification_service.settings, "telegram_br_chat_ids", "9")
    monkeypatch.setattr(notification_service.settings, "telegram_br_bot_token", "br-token-123")
    monkeypatch.setattr(
        notification_service,
        "send_telegram_message",
        lambda message, chat_ids=None, route="primary": sent_messages.append((message, chat_ids, route)) or (chat_ids or []),
    )

    with Session(engine) as session:
        report = telegram_canary_service.enqueue_and_dispatch_telegram_canary(
            session,
            route="br",
        )
        notifications = session.exec(select(Notification)).all()

    assert report["ok"] is True
    assert report["route"] == "br"
    assert report["expected_recipients"] == ["9"]
    assert len(notifications) == 1
    assert notifications[0].route == "br"
    assert sent_messages == [(notifications[0].message, ["9"], "br")]
