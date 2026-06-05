from sqlmodel import create_engine

from super_trader_quant.backend.app.services import operational_cycle_service


class DummyLock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def test_signal_cycle_runs_scan_resolve_dispatch_with_lock(monkeypatch):
    events = []
    monkeypatch.setattr(operational_cycle_service, "engine", create_engine("sqlite://"))
    monkeypatch.setattr(operational_cycle_service, "ProcessLock", DummyLock)
    monkeypatch.setattr(operational_cycle_service, "get_provider", lambda name: "provider")
    monkeypatch.setattr(
        operational_cycle_service,
        "scan_assets",
        lambda session, provider, timeframe="D1", symbols=None: events.append(("scan", timeframe, symbols)) or [object(), object()],
    )
    monkeypatch.setattr(
        operational_cycle_service,
        "resolve_open_signals",
        lambda session, provider: events.append("resolve") or [object()],
    )
    monkeypatch.setattr(
        operational_cycle_service,
        "dispatch_pending_notifications",
        lambda session, limit=None: events.append(("dispatch", limit)) or [object(), object(), object()],
    )
    monkeypatch.setattr(
        operational_cycle_service,
        "update_scheduler_heartbeat",
        lambda event, payload=None: events.append((event, payload)),
    )
    monkeypatch.setattr(operational_cycle_service.settings, "immediate_notification_batch_size", 123)

    report = operational_cycle_service.run_signal_cycle(
        provider_name="simulated",
        timeframe="D1",
        symbols=["AAPL"],
    )

    assert report["created_signals"] == 2
    assert report["resolved_signals"] == 1
    assert report["sent_notifications"] == 3
    assert report["simulation_only"] is True
    assert events[0] == ("scan", "D1", ["AAPL"])
    assert events[1] == "resolve"
    assert events[2] == ("dispatch", 123)
    assert events[3][0] == "manual_signal_cycle"


def test_signal_cycle_skips_when_lock_is_held(monkeypatch):
    def raise_lock(path):
        raise operational_cycle_service.AlreadyRunningError("ocupado")

    monkeypatch.setattr(operational_cycle_service, "ProcessLock", raise_lock)

    report = operational_cycle_service.run_signal_cycle(provider_name="simulated")

    assert report["skipped"] is True
    assert report["created_signals"] == 0
    assert "ocupado" in report["reason"]
