"""Pydantic v2 schemas for enriched gold-layer daily financial features."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DailyFeatures(BaseModel):
    """Enriched daily market metrics and technical indicators for gold_daily_features table."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    symbol: str = Field(..., description="Asset ticker symbol")
    date: dt.date = Field(..., description="Trading date")
    open: float = Field(..., ge=0.0)
    high: float = Field(..., ge=0.0)
    low: float = Field(..., ge=0.0)
    close: float = Field(..., ge=0.0)
    adjusted_close: float | None = Field(None, ge=0.0)
    volume: int = Field(..., ge=0)

    # Derived Financial Features
    daily_return_pct: float | None = Field(None, description="Daily percentage return vs previous session")
    volatility_21d: float | None = Field(
        None,
        description="21-day rolling annualized volatility (standard deviation * sqrt(252))",
    )
    volume_avg_21d: float | None = Field(None, description="21-day simple moving average of traded volume")
    max_drawdown_252d: float | None = Field(None, description="Rolling 252-day maximum drawdown in percent")

    # Technical Indicators
    sma_7: float | None = Field(None, description="7-day Simple Moving Average")
    sma_21: float | None = Field(None, description="21-day Simple Moving Average")
    sma_50: float | None = Field(None, description="50-day Simple Moving Average")
    rsi_14: float | None = Field(None, ge=0.0, le=100.0, description="14-period Relative Strength Index")
    macd_line: float | None = Field(None, description="MACD Line (12 EMA - 26 EMA)")
    macd_signal: float | None = Field(None, description="MACD Signal Line (9 EMA of MACD Line)")
    macd_hist: float | None = Field(None, description="MACD Histogram (MACD Line - Signal Line)")

    ingested_at: dt.datetime = Field(..., description="Timestamp of feature generation")

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
            "daily_return_pct": self.daily_return_pct,
            "volatility_21d": self.volatility_21d,
            "volume_avg_21d": self.volume_avg_21d,
            "max_drawdown_252d": self.max_drawdown_252d,
            "sma_7": self.sma_7,
            "sma_21": self.sma_21,
            "sma_50": self.sma_50,
            "rsi_14": self.rsi_14,
            "macd_line": self.macd_line,
            "macd_signal": self.macd_signal,
            "macd_hist": self.macd_hist,
            "ingested_at": self.ingested_at.isoformat(),
        }
