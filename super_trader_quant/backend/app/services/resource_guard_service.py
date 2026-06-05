from __future__ import annotations

import shutil
from pathlib import Path

from ..config import ROOT_DIR, settings


def sqlite_path_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw = database_url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _free_mb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(path)
    return round(usage.free / (1024 * 1024), 2)


def collect_resource_metrics() -> dict[str, object]:
    database_path = sqlite_path_from_url(settings.database_url)
    database_parent = database_path.parent if database_path else ROOT_DIR / "data"
    database_size_mb = 0.0
    if database_path and database_path.exists():
        database_size_mb = round(database_path.stat().st_size / (1024 * 1024), 2)

    paths = {
        "database_parent": database_parent,
        "log_dir": settings.resolved_log_dir,
        "backup_dir": settings.resolved_backup_dir,
    }
    free_mb_by_path = {
        name: _free_mb(path)
        for name, path in paths.items()
    }
    low_disk_paths = [
        name
        for name, free_mb in free_mb_by_path.items()
        if free_mb < settings.min_free_disk_mb
    ]
    database_size_exceeded = database_size_mb > settings.max_database_size_mb
    return {
        "database_path": str(database_path) if database_path else None,
        "database_size_mb": database_size_mb,
        "max_database_size_mb": settings.max_database_size_mb,
        "free_disk_mb_by_path": free_mb_by_path,
        "min_free_disk_mb": settings.min_free_disk_mb,
        "low_disk_paths": low_disk_paths,
        "database_size_exceeded": database_size_exceeded,
        "resource_guard_ok": not low_disk_paths and not database_size_exceeded,
    }
