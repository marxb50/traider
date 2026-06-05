from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel
from ..time_utils import utc_now_naive


class SetupMemory(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "asset_symbol",
            "strategy",
            "timeframe",
            name="uq_setup_memory_identity",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    asset_symbol: str = Field(index=True)
    strategy: str = Field(index=True)
    timeframe: str = Field(index=True)
    total_signals: int = 0
    successes: int = 0
    failures: int = 0
    expired: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0
    last_updated: datetime = Field(default_factory=utc_now_naive)
