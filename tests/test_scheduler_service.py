from sqlmodel import create_engine

from super_trader_quant.backend.app.services import scheduler_service


def test_scan_job_dispatches_notifications_immediately(monkeypatch):
    test_engine = create_engine("sqlite://")
    events = []

    monkeypatch.setattr(scheduler_service, "engine", test_engine)
    monkeypatch.setattr(scheduler_service, "get_provider", lambda name: object())
    monkeypatch.setattr(
        scheduler_service,
        "scan_assets",
        lambda session, provider, timeframe="D1": events.append(("scan", timeframe)) or [object()],
    )
    monkeypatch.setattr(scheduler_service.settings, "scan_timeframe", "H1")
    monkeypatch.setattr(scheduler_service.settings, "immediate_notification_batch_size", 1234)

    def fake_dispatch(session, limit=None):
        events.append(("dispatch", limit))
        return [object()]

    monkeypatch.setattr(scheduler_service, "dispatch_pending_notifications", fake_dispatch)
    monkeypatch.setattr(
        scheduler_service,
        "update_scheduler_heartbeat",
        lambda event, payload=None: events.append((event, payload)),
    )

    scheduler = scheduler_service.build_scheduler()
    scan_job = scheduler.get_job("scan_job")
    assert scan_job is not None

    scan_job.func()

    assert events[0:2] == [("scan", "H1"), ("dispatch", 1234)]
    assert events[2][0] == "scan_job"
    assert events[2][1]["last_scan_created"] == 1
    assert events[2][1]["last_scan_timeframe"] == "H1"
    assert events[2][1]["last_scan_notifications_sent"] == 1


def test_resolve_job_dispatches_notifications_immediately(monkeypatch):
    test_engine = create_engine("sqlite://")
    events = []

    monkeypatch.setattr(scheduler_service, "engine", test_engine)
    monkeypatch.setattr(scheduler_service, "get_provider", lambda name: object())
    monkeypatch.setattr(
        scheduler_service,
        "resolve_open_signals",
        lambda session, provider: events.append("resolve") or [object()],
    )
    monkeypatch.setattr(scheduler_service.settings, "immediate_notification_batch_size", 1234)

    def fake_dispatch(session, limit=None):
        events.append(("dispatch", limit))
        return [object()]

    monkeypatch.setattr(scheduler_service, "dispatch_pending_notifications", fake_dispatch)
    monkeypatch.setattr(
        scheduler_service,
        "update_scheduler_heartbeat",
        lambda event, payload=None: events.append((event, payload)),
    )

    scheduler = scheduler_service.build_scheduler()
    resolve_job = scheduler.get_job("resolve_job")
    assert resolve_job is not None

    resolve_job.func()

    assert events[0:2] == ["resolve", ("dispatch", 1234)]
    assert events[2][0] == "resolve_job"
    assert events[2][1]["last_resolved_count"] == 1
    assert events[2][1]["last_resolve_notifications_sent"] == 1


def test_maintenance_job_runs_retention_and_updates_heartbeat(monkeypatch):
    test_engine = create_engine("sqlite://")
    events = []

    monkeypatch.setattr(scheduler_service, "engine", test_engine)
    monkeypatch.setattr(scheduler_service, "get_provider", lambda name: object())
    monkeypatch.setattr(
        scheduler_service,
        "run_operational_maintenance",
        lambda session: {
            "deleted_sent_notifications": 2,
            "deleted_failed_notifications": 1,
            "backup_path": "/tmp/backup.db",
            "backup_error": None,
            "backup_prune_report": {"deleted_backups": ["/tmp/old.db"]},
        },
    )
    monkeypatch.setattr(
        scheduler_service,
        "update_scheduler_heartbeat",
        lambda event, payload=None: events.append((event, payload)),
    )

    scheduler = scheduler_service.build_scheduler()
    maintenance_job = scheduler.get_job("maintenance_job")
    assert maintenance_job is not None

    maintenance_job.func()

    assert events == [
        (
            "maintenance_job",
            {
                "last_maintenance_deleted_sent": 2,
                "last_maintenance_deleted_failed": 1,
                "last_maintenance_backup_path": "/tmp/backup.db",
                "last_maintenance_backup_error": None,
                "last_maintenance_deleted_backups": 1,
            },
        )
    ]
