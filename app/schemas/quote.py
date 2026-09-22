"""Pydantic v2 schemas for real-time and latest asset quotes."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GlobalQuoteClean(BaseModel):
    """Cleaned, validated quote record for Silver and Gold market snapshots."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    symbol: str = Field(..., description="Asset ticker symbol, e.g. PETR4.SAO, AAPL")
    open: float = Field(..., ge=0.0, description="Opening price of the day")
    high: float = Field(..., ge=0.0, description="Highest price of the day")
    low: float = Field(..., ge=0.0, description="Lowest price of the day")
    price: float = Field(..., ge=0.0, description="Current / Latest trading price")
    volume: int = Field(..., ge=0, description="Volume traded on the day")
    latest_trading_day: dt.date = Field(..., description="Date of the last trade")
    previous_close: float = Field(..., ge=0.0, description="Previous session closing price")
    change: float = Field(..., description="Absolute price change from previous close")
    change_percent: float = Field(..., description="Percentage change from previous close (e.g. 1.25 for +1.25%)")
    ingested_at: dt.datetime = Field(..., description="UTC/Sao Paulo timestamp when record was processed")

    @field_validator("change_percent", mode="before")
    @classmethod
    def parse_change_percent(cls, v: Any) -> float:
        """Parses strings with % suffix like '1.25%' into float 1.25."""
        if isinstance(v, str):
            clean_str = v.replace("%", "").strip()
            return float(clean_str)
        return float(v)

    def to_dict(self) -> dict[str, Any]:
        """Converts model to dictionary with serializable dates."""
        return {
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "price": self.price,
            "volume": self.volume,
            "latest_trading_day": self.latest_trading_day.isoformat(),
            "previous_close": self.previous_close,
            "change": self.change,
            "change_percent": self.change_percent,
            "ingested_at": self.ingested_at.isoformat(),
        }
