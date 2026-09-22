"""Database schema definition, partitioning, clustering, and table provisioning."""

import sqlite3
from pathlib import Path
from typing import Any

from app.config import logger, settings


def get_sqlite_schema() -> str:
    """Returns SQLite DDL for local fallback storage."""
    return """
    CREATE TABLE IF NOT EXISTS bronze_quotes_raw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_endpoint TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS bronze_timeseries_raw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_endpoint TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS silver_timeseries_daily (
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        adjusted_close REAL,
        volume INTEGER NOT NULL,
        dividend_amount REAL DEFAULT 0.0,
        split_coefficient REAL DEFAULT 1.0,
        ingested_at TEXT NOT NULL,
        PRIMARY KEY (symbol, date)
    );

    CREATE TABLE IF NOT EXISTS gold_daily_features (
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        adjusted_close REAL,
        volume INTEGER NOT NULL,
        daily_return_pct REAL,
        volatility_21d REAL,
        volume_avg_21d REAL,
        max_drawdown_252d REAL,
        sma_7 REAL,
        sma_21 REAL,
        sma_50 REAL,
        rsi_14 REAL,
        macd_line REAL,
        macd_signal REAL,
        macd_hist REAL,
        ingested_at TEXT NOT NULL,
        PRIMARY KEY (symbol, date)
    );

    CREATE TABLE IF NOT EXISTS gold_latest_quotes (
        symbol TEXT PRIMARY KEY,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        price REAL NOT NULL,
        volume INTEGER NOT NULL,
        latest_trading_day TEXT NOT NULL,
        previous_close REAL NOT NULL,
        change REAL NOT NULL,
        change_percent REAL NOT NULL,
        ingested_at TEXT NOT NULL
    );
    """


def setup_local_infrastructure(base_dir: Path | None = None) -> Path:
    """Initializes local filesystem directories and SQLite database.

    Args:
        base_dir: Optional base path. Defaults to settings.local_data_dir.

    Returns:
        Path to initialized SQLite database file.
    """
    data_dir = base_dir or settings.local_data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "bronze").mkdir(parents=True, exist_ok=True)
    (data_dir / "silver").mkdir(parents=True, exist_ok=True)
    (data_dir / "gold").mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "market_data.db"
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(get_sqlite_schema())
        logger.info("local_sqlite_initialized path=%s", db_path)
    finally:
        conn.close()

    return db_path


def setup_bigquery_infrastructure(
    client: Any,
    dataset_id: str | None = None,
    location: str | None = None,
) -> None:
    """Provisions BigQuery dataset and Medallion tables with partitioning and clustering.

    Args:
        client: BigQuery client instance.
        dataset_id: Dataset identifier. Defaults to settings.bigquery_dataset.
        location: Geographic dataset location. Defaults to settings.bigquery_location.
    """
    from google.cloud import bigquery

    dataset_name = dataset_id or settings.bigquery_dataset
    loc = location or settings.bigquery_location
    dataset_ref = bigquery.DatasetReference(client.project, dataset_name)

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = loc
    dataset = client.create_dataset(dataset, exists_ok=True)
    logger.info("bigquery_dataset_ready dataset=%s location=%s", dataset.dataset_id, loc)

    bronze_quotes_table = bigquery.Table(
        dataset_ref.table("bronze_quotes_raw"),
        schema=[
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("payload_json", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("source_endpoint", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    bronze_quotes_table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="ingested_at",
    )
    bronze_quotes_table.clustering_fields = ["symbol"]
    client.create_table(bronze_quotes_table, exists_ok=True)

    bronze_ts_table = bigquery.Table(
        dataset_ref.table("bronze_timeseries_raw"),
        schema=[
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("payload_json", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("source_endpoint", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    bronze_ts_table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="ingested_at",
    )
    bronze_ts_table.clustering_fields = ["symbol"]
    client.create_table(bronze_ts_table, exists_ok=True)

    silver_table = bigquery.Table(
        dataset_ref.table("silver_timeseries_daily"),
        schema=[
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("open", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("high", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("low", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("close", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("adjusted_close", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("volume", "INT64", mode="REQUIRED"),
            bigquery.SchemaField("dividend_amount", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("split_coefficient", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    silver_table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="date",
    )
    silver_table.clustering_fields = ["symbol"]
    client.create_table(silver_table, exists_ok=True)

    gold_features_table = bigquery.Table(
        dataset_ref.table("gold_daily_features"),
        schema=[
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("open", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("high", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("low", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("close", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("adjusted_close", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("volume", "INT64", mode="REQUIRED"),
            bigquery.SchemaField("daily_return_pct", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("volatility_21d", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("volume_avg_21d", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("max_drawdown_252d", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("sma_7", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("sma_21", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("sma_50", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("rsi_14", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("macd_line", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("macd_signal", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("macd_hist", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    gold_features_table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="date",
    )
    gold_features_table.clustering_fields = ["symbol"]
    client.create_table(gold_features_table, exists_ok=True)

    gold_quotes_table = bigquery.Table(
        dataset_ref.table("gold_latest_quotes"),
        schema=[
            bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("open", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("high", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("low", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("price", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("volume", "INT64", mode="REQUIRED"),
            bigquery.SchemaField("latest_trading_day", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("previous_close", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("change", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("change_percent", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )
    gold_quotes_table.clustering_fields = ["symbol"]
    client.create_table(gold_quotes_table, exists_ok=True)

    logger.info("bigquery_tables_provisioned dataset=%s", dataset_name)
