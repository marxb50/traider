from super_trader_quant.backend.app.services import heartbeat_service


def test_scheduler_heartbeat_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat_service.settings, "log_dir", str(tmp_path))
    payload = heartbeat_service.update_scheduler_heartbeat("scan_job", {"last_scan_created": 3})
    loaded = heartbeat_service.read_scheduler_heartbeat()

    assert payload["last_event"] == "scan_job"
    assert loaded is not None
    assert loaded["last_scan_created"] == 3
    assert loaded["last_event"] == "scan_job"
