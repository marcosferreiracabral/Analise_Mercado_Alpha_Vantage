"""Storage and persistence layer supporting Google Cloud BigQuery and Local fallback."""

from app.load.bigquery_loader import BigQueryLoader
from app.load.dataset_setup import (
    setup_bigquery_infrastructure,
    setup_local_infrastructure,
)
from app.load.local_loader import LocalStorageLoader
from app.load.storage_manager import StorageManager, get_storage_manager

__all__ = [
    "BigQueryLoader",
    "LocalStorageLoader",
    "StorageManager",
    "get_storage_manager",
    "setup_bigquery_infrastructure",
    "setup_local_infrastructure",
]
