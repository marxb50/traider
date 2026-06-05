from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from .ops_auth import require_ops_admin_access
from ..config import settings
from ..database import get_session
from ..engine.memory_engine import memory_consistency_report
from ..services.heartbeat_service import read_scheduler_heartbeat
from ..services.ops_metrics_service import collect_ops_metrics
from ..services.operational_cycle_service import run_signal_cycle
from ..services.watchdog_service import collect_watchdog_report

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/status")
def ops_status(session: Session = Depends(get_session)):
    return {
        "scheduler_heartbeat": read_scheduler_heartbeat(),
        **collect_ops_metrics(session),
        "memory_consistency": memory_consistency_report(session),
    }


@router.get("/watchdog")
def ops_watchdog(strict: bool = False, session: Session = Depends(get_session)):
    return collect_watchdog_report(session, strict=strict)


@router.post("/auth-check", dependencies=[Depends(require_ops_admin_access)])
def ops_auth_check():
    return {"ok": True, "message": "ops_admin_access_granted"}


@router.post("/scan-now", dependencies=[Depends(require_ops_admin_access)])
def ops_scan_now(timeframe: str = settings.scan_timeframe, symbol: list[str] | None = Query(default=None)):
    return run_signal_cycle(timeframe=timeframe, symbols=symbol)
