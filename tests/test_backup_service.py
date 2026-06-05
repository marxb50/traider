import sqlite3
import os
from datetime import datetime, timedelta, timezone

import pytest

from super_trader_quant.backend.app.services.backup_service import BackupError, backup_sqlite_database, prune_old_backups


def test_backup_sqlite_database_creates_consistent_copy(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO sample (name) VALUES ('ok')")

    backup = backup_sqlite_database(
        database_url=f"sqlite:///{source.as_posix()}",
        destination_dir=tmp_path / "backups",
        label="test backup",
    )

    assert backup.exists()
    assert "test-backup" in backup.name
    with sqlite3.connect(backup) as connection:
        rows = connection.execute("SELECT name FROM sample").fetchall()

    assert rows == [("ok",)]


def test_backup_sqlite_database_rejects_missing_db(tmp_path):
    with pytest.raises(BackupError):
        backup_sqlite_database(
            database_url=f"sqlite:///{(tmp_path / 'missing.db').as_posix()}",
            destination_dir=tmp_path / "backups",
        )


def test_prune_old_backups_deletes_only_project_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    old_backup = backup_dir / "super_trader_quant-maintenance-old.db"
    recent_backup = backup_dir / "super_trader_quant-maintenance-recent.db"
    other_file = backup_dir / "manual-other.db"
    old_backup.write_text("old", encoding="utf-8")
    recent_backup.write_text("recent", encoding="utf-8")
    other_file.write_text("other", encoding="utf-8")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
    os.utime(old_backup, (old_timestamp, old_timestamp))

    report = prune_old_backups(backup_dir, retention_days=1, max_files=10)

    assert str(old_backup) in report["deleted_backups"]
    assert not old_backup.exists()
    assert recent_backup.exists()
    assert other_file.exists()


def test_prune_old_backups_respects_max_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(3):
        path = backup_dir / f"super_trader_quant-maintenance-{index}.db"
        path.write_text(str(index), encoding="utf-8")
        timestamp = (datetime.now(timezone.utc) - timedelta(minutes=index)).timestamp()
        os.utime(path, (timestamp, timestamp))

    report = prune_old_backups(backup_dir, retention_days=999, max_files=2)

    assert len(report["deleted_backups"]) == 1
    assert report["remaining_backups"] == 2
