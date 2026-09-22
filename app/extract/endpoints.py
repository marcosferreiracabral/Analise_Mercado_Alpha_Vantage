"""Alpha Vantage API endpoints and query parameter builders."""

from enum import Enum
from typing import Any


class AlphaVantageEndpoint(str, Enum):
    """Supported Alpha Vantage API functions."""

    GLOBAL_QUOTE = "GLOBAL_QUOTE"
    TIME_SERIES_DAILY = "TIME_SERIES_DAILY"
    TIME_SERIES_DAILY_ADJUSTED = "TIME_SERIES_DAILY_ADJUSTED"
    TIME_SERIES_INTRADAY = "TIME_SERIES_INTRADAY"
    FX_DAILY = "FX_DAILY"
    DIGITAL_CURRENCY_DAILY = "DIGITAL_CURRENCY_DAILY"
    RSI = "RSI"
    MACD = "MACD"
    SMA = "SMA"


def build_quote_params(symbol: str) -> dict[str, Any]:
    """Builds query parameters for real-time global quote."""
    return {
        "function": AlphaVantageEndpoint.GLOBAL_QUOTE.value,
        "symbol": symbol.strip().upper(),
    }


def build_daily_timeseries_params(symbol: str, outputsize: str = "compact") -> dict[str, Any]:
    """Builds query parameters for daily standard time series."""
    return {
        "function": AlphaVantageEndpoint.TIME_SERIES_DAILY.value,
        "symbol": symbol.strip().upper(),
        "outputsize": outputsize,
    }


def build_fx_daily_params(
    from_symbol: str = "USD", to_symbol: str = "BRL", outputsize: str = "compact"
) -> dict[str, Any]:
    """Builds query parameters for daily foreign exchange rates."""
    return {
        "function": AlphaVantageEndpoint.FX_DAILY.value,
        "from_symbol": from_symbol.strip().upper(),
        "to_symbol": to_symbol.strip().upper(),
        "outputsize": outputsize,
    }


def build_crypto_daily_params(symbol: str = "BTC", market: str = "USD") -> dict[str, Any]:
    """Builds query parameters for digital/crypto currency daily series."""
    return {
        "function": AlphaVantageEndpoint.DIGITAL_CURRENCY_DAILY.value,
        "symbol": symbol.strip().upper(),
        "market": market.strip().upper(),
    }


def build_indicator_params(
    indicator: str,
    symbol: str,
    interval: str = "daily",
    time_period: int = 14,
    series_type: str = "close",
) -> dict[str, Any]:
    """Builds query parameters for technical indicators like RSI, MACD, SMA."""
    params: dict[str, Any] = {
        "function": indicator.strip().upper(),
        "symbol": symbol.strip().upper(),
        "interval": interval,
        "series_type": series_type,
    }
    if indicator.upper() in {"RSI", "SMA"}:
        params["time_period"] = time_period
    return params
