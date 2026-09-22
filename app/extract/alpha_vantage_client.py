"""Alpha Vantage API Client with retry, rate limiting, and robust error handling."""

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from app.config import logger, settings
from app.extract.endpoints import (
    build_crypto_daily_params,
    build_daily_timeseries_params,
    build_fx_daily_params,
    build_indicator_params,
    build_quote_params,
)
from app.extract.rate_limiter import RateLimiter


class AlphaVantageAPIError(Exception):
    """General error returned by Alpha Vantage API."""


class AlphaVantageRateLimitError(AlphaVantageAPIError):
    """Error returned when Alpha Vantage reports call frequency or quota exhaustion."""


class AlphaVantageInvalidSymbolError(AlphaVantageAPIError):
    """Error returned when symbol or parameters are invalid."""


class AlphaVantageClient:
    """Robust client for fetching financial data from Alpha Vantage."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> None:
        self.api_key = api_key or settings.alpha_vantage_api_key
        self.rate_limiter = rate_limiter or RateLimiter()
        self.timeout = timeout
        self.session = self._create_resilient_session(max_retries, backoff_factor)

    def _create_resilient_session(self, max_retries: int, backoff_factor: float) -> requests.Session:
        """Initializes requests Session with urllib3 retry and exponential backoff."""
        session = requests.Session()
        retries = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _request(self, params: dict[str, Any], force: bool = False) -> dict[str, Any]:
        """Dispatches an API request after checking rate limits, handling responses and errors."""
        # Enforce local pause and check quota
        self.rate_limiter.check_and_throttle(force=force)

        # Attach API key
        req_params = dict(params)
        req_params["apikey"] = self.api_key

        func_name = req_params.get("function", "UNKNOWN")
        symbol_name = req_params.get("symbol", req_params.get("from_symbol", "N/A"))
        logger.debug("Requesting Alpha Vantage: func=%s, symbol=%s", func_name, symbol_name)

        try:
            response = self.session.get(self.BASE_URL, params=req_params, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(
                "HTTP request error for func=%s symbol=%s: %s",
                func_name,
                symbol_name,
                exc,
            )
            raise AlphaVantageAPIError(f"HTTP request to Alpha Vantage failed: {exc}") from exc
        except ValueError as exc:
            logger.error(
                "Invalid JSON received for func=%s symbol=%s: %s",
                func_name,
                symbol_name,
                exc,
            )
            raise AlphaVantageAPIError(f"Received non-JSON response from Alpha Vantage: {exc}") from exc

        # Handle API-level error envelopes
        if "Error Message" in data:
            err_msg = data["Error Message"]
            logger.error(
                "Alpha Vantage API error response for symbol %s: %s",
                symbol_name,
                err_msg,
            )
            raise AlphaVantageInvalidSymbolError(f"Alpha Vantage error: {err_msg}")

        if "Note" in data:
            note_msg = data["Note"]
            logger.warning("Alpha Vantage rate limit notice for %s: %s", symbol_name, note_msg)
            raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit notice: {note_msg}")

        if "Information" in data:
            info_msg = data["Information"]
            logger.warning("Alpha Vantage information notice: %s", info_msg)
            if "rate limit" in info_msg.lower() or "calls per day" in info_msg.lower():
                raise AlphaVantageRateLimitError(f"Alpha Vantage quota notice: {info_msg}")

        return data

    def get_quote(self, symbol: str, force: bool = False) -> dict[str, Any]:
        """Fetches real-time quote for an equity or index symbol."""
        params = build_quote_params(symbol)
        return self._request(params, force=force)

    def get_daily_series(
        self,
        symbol: str,
        outputsize: str = "compact",
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetches daily time series (adjusted or standard)."""
        params = build_daily_timeseries_params(symbol, outputsize=outputsize)
        try:
            return self._request(params, force=force)
        except AlphaVantageInvalidSymbolError:
            # Fallback to standard daily if adjusted is unsupported for the symbol
            params["function"] = "TIME_SERIES_DAILY"
            return self._request(params, force=force)

    def get_fx_daily(
        self,
        from_symbol: str = "USD",
        to_symbol: str = "BRL",
        outputsize: str = "compact",
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetches daily foreign exchange rate series (e.g. USD/BRL)."""
        params = build_fx_daily_params(from_symbol, to_symbol, outputsize=outputsize)
        return self._request(params, force=force)

    def get_crypto_daily(
        self,
        symbol: str = "BTC",
        market: str = "USD",
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetches daily crypto time series (e.g. BTC, ETH in USD)."""
        params = build_crypto_daily_params(symbol, market=market)
        return self._request(params, force=force)

    def get_technical_indicator(
        self,
        indicator: str,
        symbol: str,
        interval: str = "daily",
        time_period: int = 14,
        series_type: str = "close",
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetches pre-calculated technical indicators (RSI, MACD, SMA) from Alpha Vantage."""
        params = build_indicator_params(
            indicator=indicator,
            symbol=symbol,
            interval=interval,
            time_period=time_period,
            series_type=series_type,
        )
        return self._request(params, force=force)
