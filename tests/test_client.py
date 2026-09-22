"""Unit tests for Alpha Vantage HTTP Client, rate limiting, and error handling."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import SensitiveDataFilter
from app.extract.alpha_vantage_client import (
    AlphaVantageClient,
    AlphaVantageInvalidSymbolError,
    AlphaVantageRateLimitError,
)
from app.extract.rate_limiter import RateLimiter, RateLimitExceededError


def test_client_get_quote_success(global_quote_fixture, mock_rate_limiter):
    client = AlphaVantageClient(api_key="TEST_API_KEY", rate_limiter=mock_rate_limiter)
    mock_resp = MagicMock()
    mock_resp.json.return_value = global_quote_fixture
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_resp):
        res = client.get_quote("PETR4.SAO")
        assert "Global Quote" in res
        assert res["Global Quote"]["01. symbol"] == "PETR4.SAO"


def test_client_handles_error_message(mock_rate_limiter):
    client = AlphaVantageClient(api_key="TEST_KEY", rate_limiter=mock_rate_limiter)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"Error Message": "Invalid API call. Please check your parameters."}
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(AlphaVantageInvalidSymbolError, match="Invalid API call"):
            client.get_quote("INVALID_TICKER")


def test_client_handles_rate_limit_note(mock_rate_limiter):
    client = AlphaVantageClient(api_key="TEST_KEY", rate_limiter=mock_rate_limiter)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."
    }
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(AlphaVantageRateLimitError, match="rate limit notice"):
            client.get_quote("AAPL")


def test_rate_limiter_daily_budget_exhaustion(tmp_path):
    quota_file = tmp_path / "test_quota.json"
    limiter = RateLimiter(pause_seconds=0, daily_max_requests=2, quota_file=quota_file)

    # 1st request
    c1 = limiter.check_and_throttle()
    assert c1 == 1

    # 2nd request
    c2 = limiter.check_and_throttle()
    assert c2 == 2

    # 3rd request should raise RateLimitExceededError
    with pytest.raises(RateLimitExceededError, match="daily limit reached"):
        limiter.check_and_throttle(force=False)

    # With force=True, it allows proceeding
    c3 = limiter.check_and_throttle(force=True)
    assert c3 == 3


def test_sensitive_data_filter_masks_keys():
    filt = SensitiveDataFilter(secrets_to_mask=["SECRET_KEY_12345"])
    record = MagicMock()
    record.msg = "Connecting to https://api.com?apikey=SECRET_KEY_12345 with key SECRET_KEY_12345"
    record.args = ()

    filt.filter(record)
    assert "SECRET_KEY_12345" not in record.msg
    assert "***2345" in record.msg or "***REDACTED***" in record.msg
