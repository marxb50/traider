from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from ..config import settings
from ..time_utils import utc_now_naive

HEARTBEAT_FILE = "scheduler_heartbeat.json"


def _heartbeat_path() -> Path:
    return settings.resolved_log_dir / HEARTBEAT_FILE


def update_scheduler_heartbeat(event: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    heartbeat = read_scheduler_heartbeat() or {}
    heartbeat.update(
        {
            "last_event": event,
            "last_seen_at": utc_now_naive().isoformat(),
        }
    )
    if payload:
        heartbeat.update(payload)

    target = _heartbeat_path()
    with NamedTemporaryFile("w", delete=False, dir=target.parent, encoding="utf-8") as tmp:
        json.dump(heartbeat, tmp, ensure_ascii=False, indent=2)
        temp_path = Path(tmp.name)
    temp_path.replace(target)
    return heartbeat


def read_scheduler_heartbeat() -> dict[str, object] | None:
    path = _heartbeat_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
