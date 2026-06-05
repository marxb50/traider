from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..database import get_session
from ..models.asset import Asset

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
def list_assets(session: Session = Depends(get_session)):
    return session.exec(select(Asset)).all()
