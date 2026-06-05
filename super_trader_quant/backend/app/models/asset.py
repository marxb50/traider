from typing import Optional
from sqlmodel import Field, SQLModel


class Asset(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, unique=True)
    market: str = Field(index=True)
    country: str = Field(index=True)
    sector: Optional[str] = Field(default=None, index=True)
    active: bool = True
