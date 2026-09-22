import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure project root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import streamlit as st

from app.config import logger
from app.load.storage_manager import get_storage_manager


@st.cache_data(ttl=300, show_spinner=False)
def fetch_latest_quotes_summary() -> pd.DataFrame:
    """Retrieves snapshot of latest quotes and key metrics for all monitored symbols."""
    storage = get_storage_manager()
    try:
        # Try gold_latest_quotes first
        quotes_df = storage.query_dataframe("SELECT * FROM gold_latest_quotes ORDER BY symbol")
        if not quotes_df.empty:
            return quotes_df
    except Exception as e:
        logger.debug("Failed querying gold_latest_quotes: %s", e)

    # Fallback: extract latest entry per symbol from gold_daily_features
    try:
        query = """
        SELECT
            g.symbol,
            g.open,
            g.high,
            g.low,
            g.close as price,
            g.volume,
            g.date as latest_trading_day,
            g.close - (g.close * g.daily_return_pct / 100.0) as previous_close,
            (g.close * g.daily_return_pct / 100.0) as change,
            g.daily_return_pct as change_percent,
            g.ingested_at
        FROM gold_daily_features g
        INNER JOIN (
            SELECT symbol, MAX(date) as max_date
            FROM gold_daily_features
            GROUP BY symbol
        ) m ON g.symbol = m.symbol AND g.date = m.max_date
        ORDER BY g.symbol
        """
        return storage.query_dataframe(query)
    except Exception as exc:
        logger.warning("Error fetching quotes summary: %s", exc)
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def fetch_symbol_history(symbol: str, days: int | None = None) -> pd.DataFrame:
    """Retrieves daily OHLCV and technical features for a specific symbol."""
    storage = get_storage_manager()
    sym = symbol.strip().upper()

    date_filter = ""
    if days is not None and days > 0:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_filter = f"AND date >= '{cutoff_date}'"

    query = f"""
    SELECT
        symbol,
        date,
        open,
        high,
        low,
        close,
        adjusted_close,
        volume,
        daily_return_pct,
        volatility_21d,
        volume_avg_21d,
        max_drawdown_252d,
        sma_7,
        sma_21,
        sma_50,
        rsi_14,
        macd_line,
        macd_signal,
        macd_hist,
        ingested_at
    FROM gold_daily_features
    WHERE symbol = '{sym}' {date_filter}
    ORDER BY date ASC
    """
    try:
        df = storage.query_dataframe(query)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as exc:
        logger.error("Error querying history for symbol %s: %s", sym, exc)
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def fetch_multi_symbol_history(symbols: list[str], days: int | None = None) -> pd.DataFrame:
    """Retrieves closing prices across multiple symbols for comparison."""
    if not symbols:
        return pd.DataFrame()

    storage = get_storage_manager()
    symbols_list_str = "', '".join([s.strip().upper() for s in symbols])

    date_filter = ""
    if days is not None and days > 0:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_filter = f"AND date >= '{cutoff_date}'"

    query = f"""
    SELECT
        symbol,
        date,
        close,
        daily_return_pct
    FROM gold_daily_features
    WHERE symbol IN ('{symbols_list_str}') {date_filter}
    ORDER BY date ASC
    """
    try:
        df = storage.query_dataframe(query)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as exc:
        logger.error("Error querying multi-symbol history: %s", exc)
        return pd.DataFrame()


def get_available_symbols() -> list[str]:
    """Returns list of distinct symbols present in the database."""
    storage = get_storage_manager()
    try:
        df = storage.query_dataframe("SELECT DISTINCT symbol FROM silver_timeseries_daily ORDER BY symbol")
        if not df.empty:
            return df["symbol"].tolist()
    except Exception:
        pass
    return []


def get_pipeline_metadata() -> dict[str, Any]:
    """Retrieves pipeline runtime statistics."""
    storage = get_storage_manager()
    return storage.get_storage_status()
