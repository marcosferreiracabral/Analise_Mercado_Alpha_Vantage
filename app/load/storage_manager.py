"""Unified storage manager abstracting Google Cloud BigQuery and Local Storage."""

from datetime import datetime
from typing import Any

import pandas as pd

from app.config import logger, settings
from app.load.bigquery_loader import BigQueryLoader
from app.load.local_loader import LocalStorageLoader
from app.schemas.features import DailyFeatures
from app.schemas.quote import GlobalQuoteClean
from app.schemas.timeseries import DailyBarClean


class StorageManager:
    """Unified storage interface providing seamless BigQuery and Local persistence."""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or settings.storage_mode).lower()
        self.local_loader = LocalStorageLoader()
        self.bq_loader: BigQueryLoader | None = None
        self._active_backend: str = "local"

        self._initialize_backend()

    def _initialize_backend(self) -> None:
        if self.mode in {"bigquery", "auto"}:
            if settings.is_bigquery_configured:
                try:
                    self.bq_loader = BigQueryLoader()
                    self.bq_loader.ensure_dataset_and_tables()
                    self._active_backend = "bigquery"
                    logger.info("storage_backend_active backend=bigquery project=%s", settings.gcp_project_id)
                    return
                except Exception as exc:
                    logger.warning("bigquery_init_failed error=%s fallback=local", exc)
            elif self.mode == "bigquery":
                raise RuntimeError(
                    "STORAGE_MODE='bigquery' requested but GCP_PROJECT_ID or valid credentials are not configured in .env."
                )

        self._active_backend = "local"
        self.local_loader.ensure_infrastructure()
        logger.info("storage_backend_active backend=local path=%s", settings.local_data_dir)

    @property
    def active_backend(self) -> str:
        """Returns active storage backend identifier ('bigquery' or 'local')."""
        return self._active_backend

    def ensure_setup(self) -> None:
        """Initializes tables, datasets, and local directories."""
        if self._active_backend == "bigquery" and self.bq_loader:
            self.bq_loader.ensure_dataset_and_tables()
        self.local_loader.ensure_infrastructure()

    def save_bronze_raw(
        self,
        symbol: str,
        payload: dict[str, Any],
        endpoint_type: str,
        ingested_at: datetime | None = None,
    ) -> None:
        """Persists raw JSON to Bronze layer.

        Args:
            symbol: Asset ticker symbol.
            payload: Raw response payload.
            endpoint_type: Source endpoint name.
            ingested_at: Ingestion timestamp.
        """
        self.local_loader.save_bronze_raw(symbol, payload, endpoint_type, ingested_at)
        if self._active_backend == "bigquery" and self.bq_loader:
            self.bq_loader.save_bronze_raw(symbol, payload, endpoint_type, ingested_at)

    def save_silver_timeseries(self, bars: list[DailyBarClean]) -> int:
        """Idempotently saves cleaned bars to Silver layer.

        Args:
            bars: List of DailyBarClean instances.

        Returns:
            Number of bars persisted.
        """
        count_local = self.local_loader.save_silver_timeseries(bars)
        if self._active_backend == "bigquery" and self.bq_loader:
            return self.bq_loader.save_silver_timeseries(bars)
        return count_local

    def save_gold_features(self, features: list[DailyFeatures]) -> int:
        """Idempotently saves enriched features to Gold layer.

        Args:
            features: List of DailyFeatures instances.

        Returns:
            Number of feature rows persisted.
        """
        count_local = self.local_loader.save_gold_features(features)
        if self._active_backend == "bigquery" and self.bq_loader:
            return self.bq_loader.save_gold_features(features)
        return count_local

    def save_gold_latest_quote(self, quote: GlobalQuoteClean) -> None:
        """Upserts latest quote snapshot into Gold layer.

        Args:
            quote: GlobalQuoteClean instance.
        """
        self.local_loader.save_gold_latest_quote(quote)
        if self._active_backend == "bigquery" and self.bq_loader:
            self.bq_loader.save_gold_latest_quote(quote)

    def query_dataframe(self, query: str) -> pd.DataFrame:
        """Executes SQL query against active database.

        Args:
            query: SQL query string.

        Returns:
            Query result as pandas DataFrame.
        """
        if self._active_backend == "bigquery" and self.bq_loader:
            return self.bq_loader.query_dataframe(query)
        return self.local_loader.query_dataframe(query)

    def get_storage_status(self) -> dict[str, Any]:
        """Collects row counts and metadata across Medallion layers.

        Returns:
            Dictionary containing table counts, monitored symbols, and last ingestion timestamp.
        """
        status: dict[str, Any] = {
            "backend": self._active_backend,
            "bronze_quotes_count": 0,
            "bronze_timeseries_count": 0,
            "silver_count": 0,
            "gold_features_count": 0,
            "gold_quotes_count": 0,
            "symbols_tracked": [],
            "last_ingestion": None,
        }

        try:
            silver_df = self.query_dataframe(
                "SELECT symbol, MAX(date) as last_date, COUNT(*) as cnt FROM silver_timeseries_daily GROUP BY symbol"
            )
            gold_df = self.query_dataframe("SELECT COUNT(*) as cnt FROM gold_daily_features")
            quotes_df = self.query_dataframe(
                "SELECT symbol, price, change_percent, ingested_at FROM gold_latest_quotes"
            )

            status["silver_count"] = int(silver_df["cnt"].sum()) if not silver_df.empty else 0
            status["gold_features_count"] = int(gold_df["cnt"].iloc[0]) if not gold_df.empty else 0
            status["gold_quotes_count"] = len(quotes_df)
            status["symbols_tracked"] = silver_df["symbol"].tolist() if not silver_df.empty else []

            if not quotes_df.empty and "ingested_at" in quotes_df.columns:
                status["last_ingestion"] = str(quotes_df["ingested_at"].max())
        except Exception as exc:
            logger.warning("storage_status_query_failed error=%s", exc)

        return status


_global_storage_manager: StorageManager | None = None


def get_storage_manager() -> StorageManager:
    """Returns singleton StorageManager instance."""
    global _global_storage_manager
    if _global_storage_manager is None:
        _global_storage_manager = StorageManager()
    return _global_storage_manager
