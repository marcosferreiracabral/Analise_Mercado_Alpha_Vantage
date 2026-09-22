"""Unit tests for data cleaning, Pydantic validation, and feature calculations."""

from datetime import date

import pandas as pd

from app.transform.cleaner import (
    clean_crypto_data,
    clean_fx_data,
    clean_quote_data,
    clean_timeseries_daily_data,
)
from app.transform.features import (
    calculate_financial_features,
    calculate_macd,
    calculate_rsi,
)
from app.transform.validator import validate_quote


def test_clean_quote_data(global_quote_fixture):
    quote = clean_quote_data(global_quote_fixture, symbol="PETR4.SAO", target_tz="America/Sao_Paulo")
    assert quote is not None
    assert quote.symbol == "PETR4.SAO"
    assert quote.price == 38.95
    assert quote.open == 38.50
    assert quote.volume == 42518300
    assert quote.change_percent == 1.4323
    assert quote.latest_trading_day == date(2026, 9, 22)


def test_clean_timeseries_daily(time_series_daily_fixture):
    bars = clean_timeseries_daily_data(time_series_daily_fixture, symbol="PETR4.SAO")
    assert len(bars) == 5
    # Check chronological ordering
    assert bars[0].date == date(2026, 9, 18)
    assert bars[-1].date == date(2026, 9, 22)
    assert bars[-1].close == 38.95


def test_clean_fx_data(fx_daily_fixture):
    bars = clean_fx_data(fx_daily_fixture, symbol="USD/BRL")
    assert len(bars) == 3
    assert bars[-1].close == 5.4620
    assert bars[-1].symbol == "USD/BRL"


def test_clean_crypto_data(crypto_daily_fixture):
    bars = clean_crypto_data(crypto_daily_fixture, symbol="BTC", market="USD")
    assert len(bars) == 3
    assert bars[-1].close == 64950.00
    assert bars[-1].volume == 18450


def test_validation_rejects_corrupted_data():
    valid_dict = {
        "symbol": "VALE",
        "open": 60.0,
        "high": 61.0,
        "low": 59.5,
        "price": 60.5,
        "volume": 1000000,
        "latest_trading_day": "2026-09-22",
        "previous_close": 59.8,
        "change": 0.7,
        "change_percent": 1.17,
        "ingested_at": "2026-09-22T15:00:00-03:00",
    }
    quote, report = validate_quote(valid_dict)
    assert report.is_successful
    assert quote is not None

    invalid_dict = dict(valid_dict)
    invalid_dict["price"] = -10.0  # Invalid negative price
    invalid_quote, report_inv = validate_quote(invalid_dict)
    assert not report_inv.is_successful
    assert invalid_quote is None


def test_calculate_financial_features(time_series_daily_fixture):
    bars = clean_timeseries_daily_data(time_series_daily_fixture, symbol="PETR4.SAO")
    features = calculate_financial_features(bars)
    assert len(features) == len(bars)

    last_feat = features[-1]
    assert last_feat.symbol == "PETR4.SAO"
    assert last_feat.close == 38.95
    assert last_feat.daily_return_pct is not None
    assert last_feat.sma_7 is not None
    assert last_feat.rsi_14 is not None
    assert last_feat.macd_line is not None
    assert last_feat.macd_signal is not None
    assert last_feat.macd_hist is not None


def test_rsi_and_macd_functions():
    series = pd.Series(
        [
            10.0,
            10.5,
            11.0,
            10.8,
            11.2,
            11.5,
            11.8,
            12.0,
            11.9,
            12.2,
            12.5,
            12.3,
            12.7,
            13.0,
            13.2,
        ]
    )
    rsi = calculate_rsi(series, period=5)
    assert len(rsi) == len(series)
    assert (rsi >= 0).all() and (rsi <= 100).all()

    macd_df = calculate_macd(series, fast=3, slow=6, signal=3)
    assert "macd_line" in macd_df.columns
    assert "macd_signal" in macd_df.columns
    assert "macd_hist" in macd_df.columns
