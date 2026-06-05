from datetime import timedelta

from sqlmodel import SQLModel, Session, create_engine, select

from super_trader_quant.backend.app.models.notification import Notification
from super_trader_quant.backend.app.services import maintenance_service
from super_trader_quant.backend.app.time_utils import utc_now_naive


def test_operational_maintenance_prunes_only_old_terminal_notifications(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    now = utc_now_naive()
    monkeypatch.setattr(maintenance_service.settings, "sent_notification_retention_days", 30)
    monkeypatch.setattr(maintenance_service.settings, "failed_notification_retention_days", 90)
    monkeypatch.setattr(
        maintenance_service,
        "prune_old_backups",
        lambda: {
            "deleted_backups": [],
            "delete_errors": [],
            "remaining_backups": 0,
        },
    )

    with Session(engine) as session:
        session.add(
            Notification(
                dedupe_key="old-sent",
                kind="signal_opened",
                message="old sent",
                status="sent",
                sent_at=now - timedelta(days=31),
                created_at=now - timedelta(days=31),
            )
        )
        session.add(
            Notification(
                dedupe_key="recent-sent",
                kind="signal_opened",
                message="recent sent",
                status="sent",
                sent_at=now - timedelta(days=1),
                created_at=now - timedelta(days=1),
            )
        )
        session.add(
            Notification(
                dedupe_key="old-failed",
                kind="signal_opened",
                message="old failed",
                status="failed",
                created_at=now - timedelta(days=91),
            )
        )
        session.add(
            Notification(
                dedupe_key="old-suppressed",
                kind="signal_opened",
                message="old suppressed",
                status="suppressed",
                created_at=now - timedelta(days=91),
            )
        )
        session.add(
            Notification(
                dedupe_key="old-pending",
                kind="signal_opened",
                message="old pending",
                status="pending",
                created_at=now - timedelta(days=365),
            )
        )
        session.commit()

        report = maintenance_service.run_operational_maintenance(session, create_backup=False)
        remaining = sorted(notification.dedupe_key for notification in session.exec(select(Notification)).all())

    assert report["deleted_sent_notifications"] == 1
    assert report["deleted_failed_notifications"] == 1
    assert report["deleted_suppressed_notifications"] == 1
    assert report["backup_path"] is None
    assert report["backup_prune_report"]["deleted_backups"] == []
    assert remaining == ["old-pending", "recent-sent"]
