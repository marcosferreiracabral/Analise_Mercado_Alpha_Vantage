"""Local persistence loader implementing SQLite and Parquet storage."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import logger, settings
from app.load.dataset_setup import setup_local_infrastructure
from app.schemas.features import DailyFeatures
from app.schemas.quote import GlobalQuoteClean
from app.schemas.timeseries import DailyBarClean


class LocalStorageLoader:
    """Manages local Medallion persistence using SQLite and Parquet files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or settings.local_data_dir
        self.db_path = self.data_dir / "market_data.db"
        self.ensure_infrastructure()

    def ensure_infrastructure(self) -> None:
        """Ensures local storage directories and SQLite tables exist."""
        setup_local_infrastructure(self.data_dir)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save_bronze_raw(
        self,
        symbol: str,
        payload: dict[str, Any],
        endpoint_type: str,
        ingested_at: datetime | None = None,
    ) -> None:
        """Persists raw JSON to filesystem and indexes in SQLite bronze table.

        Args:
            symbol: Asset ticker symbol.
            payload: Raw JSON response dictionary.
            endpoint_type: Source endpoint identifier.
            ingested_at: Optional timestamp of ingestion.
        """
        ts = ingested_at or datetime.now()
        timestamp_str = ts.strftime("%Y%m%d_%H%M%S")
        safe_sym = symbol.replace(".", "_").replace("/", "_")

        bronze_file = self.data_dir / "bronze" / f"{safe_sym}_{endpoint_type.lower()}_{timestamp_str}.json"
        with open(bronze_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        table_name = "bronze_quotes_raw" if "quote" in endpoint_type.lower() else "bronze_timeseries_raw"
        with self._get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO {table_name} (symbol, payload_json, source_endpoint, ingested_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    symbol.upper().strip(),
                    json.dumps(payload),
                    endpoint_type,
                    ts.isoformat(),
                ),
            )
        logger.debug("local_bronze_saved symbol=%s path=%s", symbol, bronze_file)

    def save_silver_timeseries(self, bars: list[DailyBarClean]) -> int:
        """Idempotently writes daily bars to SQLite and updates Parquet file.

        Args:
            bars: List of DailyBarClean instances.

        Returns:
            Number of rows persisted.
        """
        if not bars:
            return 0

        records = [b.to_dict() for b in bars]
        df = pd.DataFrame(records)

        sql = """
        INSERT OR REPLACE INTO silver_timeseries_daily
        (symbol, date, open, high, low, close, adjusted_close, volume, dividend_amount, split_coefficient, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows_to_insert = [
            (
                b.symbol,
                b.date.isoformat(),
                b.open,
                b.high,
                b.low,
                b.close,
                b.adjusted_close if b.adjusted_close is not None else b.close,
                b.volume,
                b.dividend_amount,
                b.split_coefficient,
                b.ingested_at.isoformat(),
            )
            for b in bars
        ]
        with self._get_connection() as conn:
            conn.executemany(sql, rows_to_insert)

        safe_sym = bars[0].symbol.replace(".", "_").replace("/", "_")
        parquet_path = self.data_dir / "silver" / f"{safe_sym}.parquet"
        try:
            if parquet_path.exists():
                existing_df = pd.read_parquet(parquet_path)
                combined_df = (
                    pd.concat([existing_df, df], ignore_index=True)
                    .drop_duplicates(subset=["symbol", "date"], keep="last")
                    .sort_values(by="date")
                )
                combined_df.to_parquet(parquet_path, index=False)
            else:
                df.sort_values(by="date").to_parquet(parquet_path, index=False)
        except Exception as exc:
            logger.warning("parquet_write_failed path=%s error=%s", parquet_path, exc)

        logger.info(
            "local_silver_persisted symbol=%s rows=%d",
            bars[0].symbol,
            len(bars),
        )
        return len(bars)

    def save_gold_features(self, features: list[DailyFeatures]) -> int:
        """Idempotently writes enriched technical features to SQLite and Parquet.

        Args:
            features: List of DailyFeatures instances.

        Returns:
            Number of feature rows persisted.
        """
        if not features:
            return 0

        records = [f.to_dict() for f in features]
        df = pd.DataFrame(records)

        sql = """
        INSERT OR REPLACE INTO gold_daily_features (
            symbol, date, open, high, low, close, adjusted_close, volume,
            daily_return_pct, volatility_21d, volume_avg_21d, max_drawdown_252d,
            sma_7, sma_21, sma_50, rsi_14, macd_line, macd_signal, macd_hist, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows_to_insert = [
            (
                f.symbol,
                f.date.isoformat(),
                f.open,
                f.high,
                f.low,
                f.close,
                f.adjusted_close if f.adjusted_close is not None else f.close,
                f.volume,
                f.daily_return_pct,
                f.volatility_21d,
                f.volume_avg_21d,
                f.max_drawdown_252d,
                f.sma_7,
                f.sma_21,
                f.sma_50,
                f.rsi_14,
                f.macd_line,
                f.macd_signal,
                f.macd_hist,
                f.ingested_at.isoformat(),
            )
            for f in features
        ]
        with self._get_connection() as conn:
            conn.executemany(sql, rows_to_insert)

        safe_sym = features[0].symbol.replace(".", "_").replace("/", "_")
        parquet_path = self.data_dir / "gold" / f"{safe_sym}.parquet"
        try:
            if parquet_path.exists():
                existing_df = pd.read_parquet(parquet_path)
                combined_df = (
                    pd.concat([existing_df, df], ignore_index=True)
                    .drop_duplicates(subset=["symbol", "date"], keep="last")
                    .sort_values(by="date")
                )
                combined_df.to_parquet(parquet_path, index=False)
            else:
                df.sort_values(by="date").to_parquet(parquet_path, index=False)
        except Exception as exc:
            logger.warning("parquet_gold_write_failed path=%s error=%s", parquet_path, exc)

        logger.info(
            "local_gold_persisted symbol=%s rows=%d",
            features[0].symbol,
            len(features),
        )
        return len(features)

    def save_gold_latest_quote(self, quote: GlobalQuoteClean) -> None:
        """Upserts latest quote snapshot into SQLite gold_latest_quotes table.

        Args:
            quote: GlobalQuoteClean instance.
        """
        sql = """
        INSERT OR REPLACE INTO gold_latest_quotes
        (symbol, open, high, low, price, volume, latest_trading_day, previous_close, change, change_percent, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._get_connection() as conn:
            conn.execute(
                sql,
                (
                    quote.symbol,
                    quote.open,
                    quote.high,
                    quote.low,
                    quote.price,
                    quote.volume,
                    quote.latest_trading_day.isoformat(),
                    quote.previous_close,
                    quote.change,
                    quote.change_percent,
                    quote.ingested_at.isoformat(),
                ),
            )
        logger.info(
            "local_quote_updated symbol=%s price=%.2f",
            quote.symbol,
            quote.price,
        )

    def query_dataframe(self, query: str) -> pd.DataFrame:
        """Executes SQL query against SQLite database.

        Args:
            query: SQL query string.

        Returns:
            Result set as a pandas DataFrame.
        """
        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn)
