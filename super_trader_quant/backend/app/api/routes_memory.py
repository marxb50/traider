from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..database import get_session
from ..models.memory import SetupMemory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def list_memory(session: Session = Depends(get_session)):
    return session.exec(select(SetupMemory)).all()
