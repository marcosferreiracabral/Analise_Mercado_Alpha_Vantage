"""Integration tests validating idempotency across Bronze, Silver, and Gold storage layers."""

from app.transform.cleaner import clean_quote_data, clean_timeseries_daily_data
from app.transform.features import calculate_financial_features


def test_idempotent_load_silver_and_gold(temp_storage_manager, time_series_daily_fixture, global_quote_fixture):
    bars = clean_timeseries_daily_data(time_series_daily_fixture, symbol="PETR4.SAO")
    quote = clean_quote_data(global_quote_fixture, symbol="PETR4.SAO")
    features = calculate_financial_features(bars)

    assert len(bars) == 5

    temp_storage_manager.save_silver_timeseries(bars)
    temp_storage_manager.save_gold_features(features)
    temp_storage_manager.save_gold_latest_quote(quote)

    status_1 = temp_storage_manager.get_storage_status()
    assert status_1["silver_count"] == 5
    assert status_1["gold_features_count"] == 5
    assert status_1["gold_quotes_count"] == 1

    temp_storage_manager.save_silver_timeseries(bars)
    temp_storage_manager.save_gold_features(features)
    temp_storage_manager.save_gold_latest_quote(quote)

    status_2 = temp_storage_manager.get_storage_status()
    assert status_2["silver_count"] == 5
    assert status_2["gold_features_count"] == 5
    assert status_2["gold_quotes_count"] == 1

    updated_bars = [b.model_copy() for b in bars]
    updated_bars[-1].close = 40.50
    updated_features = calculate_financial_features(updated_bars)

    temp_storage_manager.save_silver_timeseries(updated_bars)
    temp_storage_manager.save_gold_features(updated_features)

    status_3 = temp_storage_manager.get_storage_status()
    assert status_3["silver_count"] == 5
    assert status_3["gold_features_count"] == 5

    df = temp_storage_manager.query_dataframe("SELECT close FROM silver_timeseries_daily WHERE date = '2026-09-22'")
    assert float(df["close"].iloc[0]) == 40.50
