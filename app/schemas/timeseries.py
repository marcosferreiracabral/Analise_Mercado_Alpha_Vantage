"""Pydantic v2 schemas for daily time series records."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DailyBarClean(BaseModel):
    """Cleaned, validated daily OHLCV bar for silver_timeseries_daily table."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    symbol: str = Field(..., description="Asset ticker symbol, e.g. PETR4.SAO, AAPL, USD/BRL")
    date: dt.date = Field(..., description="Date of the trading session")
    open: float = Field(..., ge=0.0, description="Session opening price")
    high: float = Field(..., ge=0.0, description="Session highest price")
    low: float = Field(..., ge=0.0, description="Session lowest price")
    close: float = Field(..., ge=0.0, description="Session closing price")
    adjusted_close: float | None = Field(None, ge=0.0, description="Adjusted closing price if available")
    volume: int = Field(..., ge=0, description="Session traded volume")
    dividend_amount: float = Field(default=0.0, ge=0.0, description="Dividend amount paid on ex-date")
    split_coefficient: float = Field(default=1.0, gt=0.0, description="Stock split multiplier coefficient")
    ingested_at: dt.datetime = Field(..., description="Timestamp when record was ingested/processed")

    def to_dict(self) -> dict[str, Any]:
        """Converts model to dictionary with standard types."""
        return {
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adjusted_close": self.adjusted_close if self.adjusted_close is not None else self.close,
            "volume": self.volume,
            "dividend_amount": self.dividend_amount,
            "split_coefficient": self.split_coefficient,
            "ingested_at": self.ingested_at.isoformat(),
        }
