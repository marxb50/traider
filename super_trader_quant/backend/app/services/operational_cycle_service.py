from __future__ import annotations

from sqlmodel import Session

from ..config import settings
from ..database import engine
from ..data_providers.factory import get_provider
from ..engine.scanner_engine import resolve_open_signals, scan_assets
from .heartbeat_service import update_scheduler_heartbeat
from .notification_service import dispatch_pending_notifications
from .process_lock import AlreadyRunningError, ProcessLock


def run_signal_cycle(
    *,
    provider_name: str | None = None,
    timeframe: str | None = None,
    symbols: list[str] | None = None,
    use_lock: bool = True,
    heartbeat_event: str = "manual_signal_cycle",
) -> dict[str, object]:
    """Run scan + resolution + immediate notification dispatch through one safe path."""

    provider = get_provider(provider_name or settings.default_provider)
    selected_timeframe = timeframe or settings.scan_timeframe

    def _run() -> dict[str, object]:
        with Session(engine) as session:
            created = scan_assets(session, provider, timeframe=selected_timeframe, symbols=symbols)
        with Session(engine) as session:
            resolved = resolve_open_signals(session, provider)
        with Session(engine) as session:
            sent = dispatch_pending_notifications(session, limit=settings.immediate_notification_batch_size)
        report = {
            "provider": provider_name or settings.default_provider,
            "timeframe": selected_timeframe,
            "symbols": symbols or [],
            "created_signals": len(created),
            "resolved_signals": len(resolved),
            "sent_notifications": len(sent),
            "simulation_only": True,
        }
        update_scheduler_heartbeat(
            heartbeat_event,
            {
                "last_manual_cycle_created": len(created),
                "last_manual_cycle_resolved": len(resolved),
                "last_manual_cycle_notifications_sent": len(sent),
            },
        )
        return report

    if not use_lock:
        return _run()

    try:
        with ProcessLock(settings.resolved_scheduler_lock_path):
            return _run()
    except AlreadyRunningError as exc:
        return {
            "provider": provider_name or settings.default_provider,
            "timeframe": selected_timeframe,
            "symbols": symbols or [],
            "created_signals": 0,
            "resolved_signals": 0,
            "sent_notifications": 0,
            "simulation_only": True,
            "skipped": True,
            "reason": str(exc),
        }
