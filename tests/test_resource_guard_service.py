from super_trader_quant.backend.app.services import resource_guard_service


def test_resource_guard_reports_db_size_and_disk_space(monkeypatch, tmp_path):
    db_path = tmp_path / "data" / "super_trader_quant.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"x" * 1024)

    monkeypatch.setattr(resource_guard_service.settings, "database_url", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(resource_guard_service.settings, "log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(resource_guard_service.settings, "backup_dir", str(tmp_path / "data" / "backups"))
    monkeypatch.setattr(resource_guard_service.settings, "min_free_disk_mb", 0)
    monkeypatch.setattr(resource_guard_service.settings, "max_database_size_mb", 10)

    metrics = resource_guard_service.collect_resource_metrics()

    assert metrics["database_path"] == str(db_path.resolve())
    assert metrics["database_size_mb"] >= 0
    assert metrics["database_size_exceeded"] is False
    assert metrics["low_disk_paths"] == []
    assert metrics["resource_guard_ok"] is True


def test_resource_guard_flags_database_size_limit(monkeypatch, tmp_path):
    db_path = tmp_path / "data" / "super_trader_quant.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"x" * 2048)

    monkeypatch.setattr(resource_guard_service.settings, "database_url", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(resource_guard_service.settings, "log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(resource_guard_service.settings, "backup_dir", str(tmp_path / "data" / "backups"))
    monkeypatch.setattr(resource_guard_service.settings, "min_free_disk_mb", 0)
    monkeypatch.setattr(resource_guard_service.settings, "max_database_size_mb", -1)

    metrics = resource_guard_service.collect_resource_metrics()

    assert metrics["database_size_exceeded"] is True
    assert metrics["resource_guard_ok"] is False
