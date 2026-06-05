from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine
from super_trader_quant.backend.app.models.signal import Signal


def test_signal_identity_is_unique():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        payload = {
            "asset_symbol": "PETR4.SA",
            "market": "BR",
            "strategy": "IFR2",
            "timeframe": "D1",
            "signal_time": datetime(2026, 1, 1),
            "entry": 100,
            "stop": 95,
            "target": 110,
        }
        session.add(Signal(**payload))
        session.add(Signal(**payload))
        with pytest.raises(IntegrityError):
            session.commit()
