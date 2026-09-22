"""Google Cloud BigQuery loader with partitioned tables and idempotent operations."""

import json
import re
from datetime import datetime
from typing import Any

import pandas as pd
from google.cloud import bigquery

from app.config import logger, settings
from app.load.dataset_setup import setup_bigquery_infrastructure
from app.schemas.features import DailyFeatures
from app.schemas.quote import GlobalQuoteClean
from app.schemas.timeseries import DailyBarClean


class BigQueryLoader:
    """Handles idempotent persistence into BigQuery Medallion tables."""

    def __init__(
        self,
        client: bigquery.Client | None = None,
        project_id: str | None = None,
        dataset_id: str | None = None,
    ) -> None:
        self.project_id = project_id or settings.gcp_project_id
        self.dataset_id = dataset_id or settings.bigquery_dataset
        self.client = client or bigquery.Client(project=self.project_id)
        self.dataset_ref = f"{self.client.project}.{self.dataset_id}"

    def ensure_dataset_and_tables(self) -> None:
        """Provisions datasets and tables if not already present."""
        setup_bigquery_infrastructure(self.client, self.dataset_id, settings.bigquery_location)

    def save_bronze_raw(
        self,
        symbol: str,
        payload: dict[str, Any],
        endpoint_type: str,
        ingested_at: datetime | None = None,
    ) -> None:
        """Appends raw JSON payload into bronze staging table.

        Args:
            symbol: Asset ticker symbol.
            payload: Raw API response dictionary.
            endpoint_type: Endpoint name.
            ingested_at: Optional timestamp.
        """
        table_name = "bronze_quotes_raw" if "quote" in endpoint_type.lower() else "bronze_timeseries_raw"
        table_ref = f"{self.dataset_ref}.{table_name}"
        rows_to_insert = [
            {
                "symbol": symbol.upper().strip(),
                "payload_json": json.dumps(payload),
                "source_endpoint": endpoint_type,
                "ingested_at": (ingested_at or datetime.utcnow()).isoformat(),
            }
        ]
        try:
            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            )
            self.client.load_table_from_json(rows_to_insert, table_ref, job_config=job_config).result()
            logger.debug("bigquery_bronze_appended symbol=%s endpoint=%s", symbol, endpoint_type)
        except Exception as exc:
            logger.warning("bigquery_bronze_failed table=%s error=%s", table_name, exc)

    def _execute_merge_or_direct_load(
        self,
        df: pd.DataFrame,
        table_ref: str,
        staging_table_ref: str,
        merge_sql: str,
        is_snapshot: bool = False,
    ) -> None:
        """Executes SQL MERGE when billing is active, or fallback LoadJob for BigQuery Sandbox."""
        try:
            query_job = self.client.query(merge_sql)
            query_job.result()
        except Exception as exc:
            err_msg = str(exc).lower()
            if "billing" in err_msg or "dml queries are not allowed" in err_msg or "403" in err_msg:
                logger.info("bigquery_sandbox_fallback mode=direct_load table=%s", table_ref)
                disposition = (
                    bigquery.WriteDisposition.WRITE_TRUNCATE
                    if is_snapshot
                    else bigquery.WriteDisposition.WRITE_APPEND
                )
                job_config = bigquery.LoadJobConfig(
                    write_disposition=disposition,
                )
                chunk_size = 1500
                if len(df) > chunk_size and not is_snapshot:
                    for i in range(0, len(df), chunk_size):
                        sub_df = df.iloc[i : i + chunk_size]
                        self.client.load_table_from_dataframe(sub_df, table_ref, job_config=job_config).result()
                else:
                    self.client.load_table_from_dataframe(df, table_ref, job_config=job_config).result()
            else:
                raise
        finally:
            self.client.delete_table(staging_table_ref, not_found_ok=True)

    def save_silver_timeseries(self, bars: list[DailyBarClean]) -> int:
        """Idempotently merges cleaned daily bars into silver_timeseries_daily.

        Args:
            bars: List of DailyBarClean instances.

        Returns:
            Number of rows persisted.
        """
        if not bars:
            return 0

        clean_sym = re.sub(r"[^a-zA-Z0-9_]", "_", bars[0].symbol)
        table_ref = f"{self.dataset_ref}.silver_timeseries_daily"
        staging_table_id = f"stg_silver_{clean_sym}_{int(datetime.utcnow().timestamp())}"
        staging_table_ref = f"{self.dataset_ref}.{staging_table_id}"

        records = [b.to_dict() for b in bars]
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["ingested_at"] = pd.to_datetime(df["ingested_at"])

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=True,
        )
        load_job = self.client.load_table_from_dataframe(df, staging_table_ref, job_config=job_config)
        load_job.result()

        merge_sql = f"""
        MERGE `{table_ref}` T
        USING `{staging_table_ref}` S
        ON T.symbol = S.symbol AND T.date = S.date
        WHEN MATCHED THEN
          UPDATE SET
            T.open = S.open,
            T.high = S.high,
            T.low = S.low,
            T.close = S.close,
            T.adjusted_close = S.adjusted_close,
            T.volume = S.volume,
            T.dividend_amount = S.dividend_amount,
            T.split_coefficient = S.split_coefficient,
            T.ingested_at = S.ingested_at
        WHEN NOT MATCHED THEN
          INSERT (symbol, date, open, high, low, close, adjusted_close, volume, dividend_amount, split_coefficient, ingested_at)
          VALUES (S.symbol, S.date, S.open, S.high, S.low, S.close, S.adjusted_close, S.volume, S.dividend_amount, S.split_coefficient, S.ingested_at)
        """
        self._execute_merge_or_direct_load(df, table_ref, staging_table_ref, merge_sql, is_snapshot=False)
        logger.info("bigquery_silver_saved symbol=%s rows=%d", bars[0].symbol, len(bars))
        return len(bars)

    def save_gold_features(self, features: list[DailyFeatures]) -> int:
        """Idempotently merges enriched features into gold_daily_features.

        Args:
            features: List of DailyFeatures instances.

        Returns:
            Number of rows persisted.
        """
        if not features:
            return 0

        clean_sym = re.sub(r"[^a-zA-Z0-9_]", "_", features[0].symbol)
        table_ref = f"{self.dataset_ref}.gold_daily_features"
        staging_table_id = f"stg_gold_{clean_sym}_{int(datetime.utcnow().timestamp())}"
        staging_table_ref = f"{self.dataset_ref}.{staging_table_id}"

        records = [f.to_dict() for f in features]
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["ingested_at"] = pd.to_datetime(df["ingested_at"])

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=True,
        )
        load_job = self.client.load_table_from_dataframe(df, staging_table_ref, job_config=job_config)
        load_job.result()

        merge_sql = f"""
        MERGE `{table_ref}` T
        USING `{staging_table_ref}` S
        ON T.symbol = S.symbol AND T.date = S.date
        WHEN MATCHED THEN
          UPDATE SET
            T.open = S.open,
            T.high = S.high,
            T.low = S.low,
            T.close = S.close,
            T.adjusted_close = S.adjusted_close,
            T.volume = S.volume,
            T.daily_return_pct = S.daily_return_pct,
            T.volatility_21d = S.volatility_21d,
            T.volume_avg_21d = S.volume_avg_21d,
            T.max_drawdown_252d = S.max_drawdown_252d,
            T.sma_7 = S.sma_7,
            T.sma_21 = S.sma_21,
            T.sma_50 = S.sma_50,
            T.rsi_14 = S.rsi_14,
            T.macd_line = S.macd_line,
            T.macd_signal = S.macd_signal,
            T.macd_hist = S.macd_hist,
            T.ingested_at = S.ingested_at
        WHEN NOT MATCHED THEN
          INSERT (
            symbol, date, open, high, low, close, adjusted_close, volume,
            daily_return_pct, volatility_21d, volume_avg_21d, max_drawdown_252d,
            sma_7, sma_21, sma_50, rsi_14, macd_line, macd_signal, macd_hist, ingested_at
          )
          VALUES (
            S.symbol, S.date, S.open, S.high, S.low, S.close, S.adjusted_close, S.volume,
            S.daily_return_pct, S.volatility_21d, S.volume_avg_21d, S.max_drawdown_252d,
            S.sma_7, S.sma_21, S.sma_50, S.rsi_14, S.macd_line, S.macd_signal, S.macd_hist, S.ingested_at
          )
        """
        self._execute_merge_or_direct_load(df, table_ref, staging_table_ref, merge_sql, is_snapshot=False)
        logger.info("bigquery_gold_saved symbol=%s rows=%d", features[0].symbol, len(features))
        return len(features)

    def save_gold_latest_quote(self, quote: GlobalQuoteClean) -> None:
        """Upserts latest snapshot quote into gold_latest_quotes.

        Args:
            quote: GlobalQuoteClean instance.
        """
        clean_sym = re.sub(r"[^a-zA-Z0-9_]", "_", quote.symbol)
        table_ref = f"{self.dataset_ref}.gold_latest_quotes"
        df = pd.DataFrame([quote.to_dict()])
        df["latest_trading_day"] = pd.to_datetime(df["latest_trading_day"]).dt.date
        df["ingested_at"] = pd.to_datetime(df["ingested_at"])

        staging_table_ref = (
            f"{self.dataset_ref}.stg_quote_{clean_sym}_{int(datetime.utcnow().timestamp())}"
        )
        job_config = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE, autodetect=True)
        self.client.load_table_from_dataframe(df, staging_table_ref, job_config=job_config).result()

        merge_sql = f"""
        MERGE `{table_ref}` T
        USING `{staging_table_ref}` S
        ON T.symbol = S.symbol
        WHEN MATCHED THEN
          UPDATE SET
            T.open = S.open,
            T.high = S.high,
            T.low = S.low,
            T.price = S.price,
            T.volume = S.volume,
            T.latest_trading_day = S.latest_trading_day,
            T.previous_close = S.previous_close,
            T.change = S.change,
            T.change_percent = S.change_percent,
            T.ingested_at = S.ingested_at
        WHEN NOT MATCHED THEN
          INSERT (symbol, open, high, low, price, volume, latest_trading_day, previous_close, change, change_percent, ingested_at)
          VALUES (S.symbol, S.open, S.high, S.low, S.price, S.volume, S.latest_trading_day, S.previous_close, S.change, S.change_percent, S.ingested_at)
        """
        self._execute_merge_or_direct_load(df, table_ref, staging_table_ref, merge_sql, is_snapshot=True)
        logger.info("bigquery_quote_saved symbol=%s price=%.2f", quote.symbol, quote.price)

    def query_dataframe(self, query: str) -> pd.DataFrame:
        """Executes SQL query against BigQuery.

        Args:
            query: Standard SQL query string.

        Returns:
            Result set as pandas DataFrame.
        """
        job_config = bigquery.QueryJobConfig(
            default_dataset=f"{self.client.project}.{self.dataset_id}"
        )
        query_job = self.client.query(query, job_config=job_config)
        return query_job.to_dataframe()
