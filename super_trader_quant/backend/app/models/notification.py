from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlmodel import Field, SQLModel
from ..time_utils import utc_now_naive


class Notification(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    dedupe_key: str = Field(index=True, unique=True)
    kind: str = Field(index=True)
    route: str = Field(default="primary", index=True)
    chat_id: Optional[str] = Field(default=None, index=True)
    message: str
    status: str = Field(default="pending", index=True)
    attempts: int = 0
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now_naive, index=True)
    sent_at: Optional[datetime] = None
