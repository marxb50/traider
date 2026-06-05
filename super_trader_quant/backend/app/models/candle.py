from datetime import datetime
from sqlmodel import Field, SQLModel


class Candle(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    asset_symbol: str = Field(index=True)
    timeframe: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
