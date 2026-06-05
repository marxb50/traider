from datetime import datetime
from sqlmodel import Field, SQLModel
from ..time_utils import utc_now_naive


class BacktestRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    asset_symbol: str = Field(index=True)
    strategy: str = Field(index=True)
    timeframe: str = Field(index=True)
    started_at: datetime = Field(default_factory=utc_now_naive)
    total_return_pct: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    trades: int
