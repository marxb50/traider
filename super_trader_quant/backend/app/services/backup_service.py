from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import ROOT_DIR, settings


class BackupError(RuntimeError):
    """Raised when a database backup cannot be created safely."""


BACKUP_GLOB = "super_trader_quant-*.db"


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise BackupError("Backup automático só é suportado para SQLite no MVP.")
    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _safe_label(label: str | None) -> str:
    if not label:
        return "manual"
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", label.strip()).strip("-")
    return normalized or "manual"


def backup_sqlite_database(
    database_url: str | None = None,
    destination_dir: str | Path | None = None,
    label: str | None = None,
) -> Path:
    """Create a consistent SQLite backup using SQLite's online backup API."""

    source = sqlite_path_from_url(database_url or settings.database_url)
    if not source.exists():
        raise BackupError(f"Banco SQLite não encontrado: {source}")

    destination = Path(destination_dir) if destination_dir is not None else settings.resolved_backup_dir
    if not destination.is_absolute():
        destination = ROOT_DIR / destination
    destination.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_path = destination / f"super_trader_quant-{_safe_label(label)}-{timestamp}.db"

    try:
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(backup_path) as backup_connection:
                source_connection.backup(backup_connection)
    except sqlite3.Error as exc:
        try:
            backup_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupError(f"Falha ao criar backup SQLite: {exc}") from exc

    return backup_path


def prune_old_backups(
    destination_dir: str | Path | None = None,
    *,
    retention_days: int | None = None,
    max_files: int | None = None,
) -> dict[str, object]:
    destination = Path(destination_dir) if destination_dir is not None else settings.resolved_backup_dir
    if not destination.is_absolute():
        destination = ROOT_DIR / destination
    destination.mkdir(parents=True, exist_ok=True)

    keep_days = settings.backup_retention_days if retention_days is None else retention_days
    keep_max_files = settings.backup_retention_max_files if max_files is None else max_files
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    backups = sorted(
        [path for path in destination.glob(BACKUP_GLOB) if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    to_delete: list[Path] = []
    for index, path in enumerate(backups):
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        too_old = keep_days >= 0 and modified_at < cutoff
        above_count = keep_max_files >= 0 and index >= keep_max_files
        if too_old or above_count:
            to_delete.append(path)

    deleted: list[str] = []
    errors: list[str] = []
    for path in to_delete:
        try:
            path.unlink()
            deleted.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    remaining = len([path for path in destination.glob(BACKUP_GLOB) if path.is_file()])
    return {
        "backup_dir": str(destination),
        "deleted_backups": deleted,
        "delete_errors": errors,
        "remaining_backups": remaining,
        "retention_days": keep_days,
        "retention_max_files": keep_max_files,
    }
