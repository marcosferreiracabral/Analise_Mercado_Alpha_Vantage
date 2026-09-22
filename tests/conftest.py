"""Pytest fixtures for unit and integration testing."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.extract.rate_limiter import RateLimiter
from app.load.storage_manager import StorageManager

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def global_quote_fixture() -> dict[str, Any]:
    with open(FIXTURES_DIR / "global_quote.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def time_series_daily_fixture() -> dict[str, Any]:
    with open(FIXTURES_DIR / "time_series_daily.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fx_daily_fixture() -> dict[str, Any]:
    with open(FIXTURES_DIR / "fx_daily.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def crypto_daily_fixture() -> dict[str, Any]:
    with open(FIXTURES_DIR / "crypto_daily.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_rate_limiter(tmp_path: Path) -> RateLimiter:
    """Returns isolated RateLimiter instance using temporary directory."""
    quota_file = tmp_path / ".test_daily_quota.json"
    return RateLimiter(pause_seconds=0, daily_max_requests=1000, quota_file=quota_file)


@pytest.fixture
def temp_storage_manager(tmp_path: Path) -> StorageManager:
    """Returns StorageManager configured in isolated temporary directory."""
    from app.config import settings

    settings.local_data_dir = tmp_path
    settings.storage_mode = "local"
    mgr = StorageManager(mode="local")
    mgr.ensure_setup()
    return mgr
