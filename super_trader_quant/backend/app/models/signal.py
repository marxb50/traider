from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel
from ..time_utils import utc_now_naive


class Signal(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "asset_symbol",
            "strategy",
            "timeframe",
            "signal_time",
            name="uq_signal_identity",
        ),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    asset_symbol: str = Field(index=True)
    market: str = Field(index=True)
    strategy: str = Field(index=True)
    timeframe: str = Field(index=True)
    signal_time: datetime = Field(index=True)
    detected_at: datetime = Field(default_factory=utc_now_naive, index=True)
    side: str = "long"
    entry: float
    stop: float
    target: float
    holding_period_bars: int = 5
    status: str = Field(default="open", index=True)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl_pct: Optional[float] = None
    outcome_checked_at: Optional[datetime] = None
    memory_applied_at: Optional[datetime] = None
    alert_level: Optional[str] = Field(default=None, index=True)
    alert_score: Optional[float] = None
    alert_probability_pct: Optional[float] = None
    alert_sample_size: int = 0
    alert_avg_bars_to_target: Optional[float] = None
    alert_risk_reward: Optional[float] = None
    alert_reason: Optional[str] = None
    data_provider: Optional[str] = Field(default=None, index=True)
    data_source_status: Optional[str] = Field(default=None, index=True)
    data_source_count: int = 0
    data_source_reason: Optional[str] = None
    data_source_audit_json: Optional[str] = None
    notes: Optional[str] = None
