from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..database import get_session
from ..models.signal import Signal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
def list_signals(session: Session = Depends(get_session), status: str | None = None):
    statement = select(Signal)
    if status:
        statement = statement.where(Signal.status == status)
    return session.exec(statement).all()
