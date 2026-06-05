from datetime import datetime
import pandas as pd
from sqlmodel import SQLModel, Session, create_engine
from super_trader_quant.backend.app.engine import scanner_engine
from super_trader_quant.backend.app.models.asset import Asset


class BatchProvider:
    def __init__(self):
        self.batch_calls = 0

    def fetch_many_history(self, symbols, timeframe="D1", period="1y"):
        self.batch_calls += 1
        frame = pd.DataFrame(
            [
                {
                    "timestamp": datetime(2026, 1, 1),
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 1,
                }
            ]
        )
        return {symbol: frame.copy() for symbol in symbols}


def test_scanner_uses_batch_fetch_when_available():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    provider = BatchProvider()
    with Session(engine) as session:
        session.add(Asset(symbol="AAPL", market="US", country="EUA"))
        session.add(Asset(symbol="MSFT", market="US", country="EUA"))
        session.commit()
        scanner_engine.scan_assets(session, provider)
    assert provider.batch_calls == 1
