"""Data cleaning, timezone normalization, and type conversion for market datasets."""

from datetime import date, datetime
from typing import Any

import pytz

from app.config import logger, settings
from app.schemas.quote import GlobalQuoteClean
from app.schemas.timeseries import DailyBarClean


def get_current_localized_timestamp(tz_name: str | None = None) -> datetime:
    """Returns current localized timestamp for ingestion tracking.

    Args:
        tz_name: Optional timezone name. Defaults to settings.default_timezone.

    Returns:
        Current timezone-aware datetime instance.
    """
    timezone = pytz.timezone(tz_name or settings.default_timezone)
    return datetime.now(timezone)


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        clean = str(val).replace("%", "").strip()
        return float(clean)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        clean = str(val).split(".")[0].strip()
        return int(clean)
    except (ValueError, TypeError):
        return default


def _parse_date(date_str: Any) -> date | None:
    if isinstance(date_str, date) and not isinstance(date_str, datetime):
        return date_str
    if isinstance(date_str, datetime):
        return date_str.date()
    if not isinstance(date_str, str):
        return None
    try:
        clean_date = date_str.strip().split(" ")[0]
        return datetime.strptime(clean_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def clean_quote_data(
    raw_json: dict[str, Any],
    symbol: str,
    target_tz: str | None = None,
) -> GlobalQuoteClean | None:
    """Extracts and normalizes raw Global Quote JSON payload.

    Args:
        raw_json: Raw payload dictionary from Alpha Vantage.
        symbol: Market ticker symbol.
        target_tz: Optional target timezone for ingestion timestamp.

    Returns:
        Validated GlobalQuoteClean instance or None if payload is invalid.
    """
    quote_payload = raw_json.get("Global Quote") or raw_json
    if not quote_payload:
        logger.warning("quote_payload_empty symbol=%s", symbol)
        return None

    symbol_val = str(quote_payload.get("01. symbol") or quote_payload.get("symbol") or symbol).upper().strip()
    open_val = _safe_float(quote_payload.get("02. open") or quote_payload.get("open"))
    high_val = _safe_float(quote_payload.get("03. high") or quote_payload.get("high"))
    low_val = _safe_float(quote_payload.get("04. low") or quote_payload.get("low"))
    price_val = _safe_float(quote_payload.get("05. price") or quote_payload.get("price"))
    volume_val = _safe_int(quote_payload.get("06. volume") or quote_payload.get("volume"))
    day_str = quote_payload.get("07. latest trading day") or quote_payload.get("latest_trading_day")
    prev_close_val = _safe_float(quote_payload.get("08. previous close") or quote_payload.get("previous_close"))
    change_val = _safe_float(quote_payload.get("09. change") or quote_payload.get("change"))
    change_pct_val = _safe_float(quote_payload.get("10. change percent") or quote_payload.get("change_percent"))

    parsed_date = _parse_date(day_str) or date.today()

    if price_val is None or open_val is None:
        logger.warning("quote_missing_price_fields symbol=%s", symbol)
        return None

    return GlobalQuoteClean(
        symbol=symbol_val,
        open=open_val,
        high=high_val if high_val is not None else max(open_val, price_val),
        low=low_val if low_val is not None else min(open_val, price_val),
        price=price_val,
        volume=volume_val,
        latest_trading_day=parsed_date,
        previous_close=prev_close_val if prev_close_val is not None else price_val,
        change=change_val if change_val is not None else 0.0,
        change_percent=change_pct_val if change_pct_val is not None else 0.0,
        ingested_at=get_current_localized_timestamp(target_tz),
    )


def clean_timeseries_daily_data(
    raw_json: dict[str, Any],
    symbol: str,
    target_tz: str | None = None,
) -> list[DailyBarClean]:
    """Parses and validates raw daily time series payload into typed daily bars.

    Args:
        raw_json: Raw JSON response from time series endpoint.
        symbol: Asset ticker symbol.
        target_tz: Optional timezone for timestamp normalization.

    Returns:
        Chronologically sorted list of DailyBarClean models.
    """
    ts_key = next((k for k in raw_json if "Time Series" in k), None)
    if not ts_key or not isinstance(raw_json[ts_key], dict):
        logger.warning("timeseries_key_missing symbol=%s", symbol)
        return []

    ts_data = raw_json[ts_key]
    cleaned_bars: list[DailyBarClean] = []
    seen_dates: set[date] = set()
    ingested_at = get_current_localized_timestamp(target_tz)

    for date_str, bar in ts_data.items():
        parsed_d = _parse_date(date_str)
        if not parsed_d or parsed_d in seen_dates:
            continue

        open_val = _safe_float(bar.get("1. open") or bar.get("1a. open (USD)") or bar.get("open"))
        high_val = _safe_float(bar.get("2. high") or bar.get("2a. high (USD)") or bar.get("high"))
        low_val = _safe_float(bar.get("3. low") or bar.get("3a. low (USD)") or bar.get("low"))
        close_val = _safe_float(bar.get("4. close") or bar.get("4a. close (USD)") or bar.get("close"))
        adj_close_val = _safe_float(bar.get("5. adjusted close") or bar.get("adjusted_close"))
        vol_val = _safe_int(bar.get("5. volume") or bar.get("6. volume") or bar.get("volume"))
        div_val = _safe_float(
            bar.get("6. dividend amount") or bar.get("7. dividend amount") or bar.get("dividend_amount"),
            0.0,
        )
        split_val = _safe_float(
            bar.get("7. split coefficient") or bar.get("8. split coefficient") or bar.get("split_coefficient"),
            1.0,
        )

        if open_val is None or high_val is None or low_val is None or close_val is None:
            logger.debug("null_price_fields_skipped symbol=%s date=%s", symbol, date_str)
            continue

        if open_val < 0 or high_val < 0 or low_val < 0 or close_val < 0:
            logger.warning("negative_price_anomaly_skipped symbol=%s date=%s", symbol, date_str)
            continue

        seen_dates.add(parsed_d)
        cleaned_bars.append(
            DailyBarClean(
                symbol=symbol.upper().strip(),
                date=parsed_d,
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                adjusted_close=adj_close_val if adj_close_val is not None else close_val,
                volume=vol_val,
                dividend_amount=div_val if div_val is not None else 0.0,
                split_coefficient=split_val if split_val is not None and split_val > 0 else 1.0,
                ingested_at=ingested_at,
            )
        )

    cleaned_bars.sort(key=lambda b: b.date)
    return cleaned_bars


def clean_fx_data(
    raw_json: dict[str, Any],
    symbol: str = "USD/BRL",
    target_tz: str | None = None,
) -> list[DailyBarClean]:
    """Cleans daily foreign exchange rate series.

    Args:
        raw_json: Raw JSON response for FX_DAILY.
        symbol: Currency pair string.
        target_tz: Optional timezone name.

    Returns:
        List of DailyBarClean instances.
    """
    return clean_timeseries_daily_data(raw_json, symbol=symbol, target_tz=target_tz)


def clean_crypto_data(
    raw_json: dict[str, Any],
    symbol: str = "BTC",
    market: str = "USD",
    target_tz: str | None = None,
) -> list[DailyBarClean]:
    """Cleans cryptocurrency daily series.

    Args:
        raw_json: Raw JSON response for DIGITAL_CURRENCY_DAILY.
        symbol: Cryptocurrency symbol.
        market: Target quote currency.
        target_tz: Optional timezone name.

    Returns:
        List of DailyBarClean instances.
    """
    sym = f"{symbol.upper()}/{market.upper()}" if "/" not in symbol else symbol.upper()
    return clean_timeseries_daily_data(raw_json, symbol=sym, target_tz=target_tz)
