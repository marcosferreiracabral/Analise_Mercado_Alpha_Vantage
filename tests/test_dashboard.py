"""Unit tests for dashboard queries and chart generation."""

import pandas as pd

from app.dashboard.charts import (
    create_comparison_chart,
    create_correlation_heatmap,
    create_macd_chart,
    create_price_and_volume_chart,
    create_risk_chart,
    create_rsi_chart,
)
from app.transform.cleaner import clean_timeseries_daily_data
from app.transform.features import calculate_financial_features


def test_chart_generation(time_series_daily_fixture, temp_storage_manager):
    bars = clean_timeseries_daily_data(time_series_daily_fixture, symbol="PETR4.SAO")
    features = calculate_financial_features(bars)
    temp_storage_manager.save_silver_timeseries(bars)
    temp_storage_manager.save_gold_features(features)

    df = temp_storage_manager.query_dataframe("SELECT * FROM gold_daily_features ORDER BY date ASC")
    df["date"] = pd.to_datetime(df["date"])

    # Test individual chart generators
    fig_price = create_price_and_volume_chart(df, chart_type="candlestick")
    assert fig_price is not None
    assert len(fig_price.data) >= 2  # Candlestick + Volume + SMAs

    fig_rsi = create_rsi_chart(df)
    assert fig_rsi is not None

    fig_macd = create_macd_chart(df)
    assert fig_macd is not None

    fig_risk = create_risk_chart(df)
    assert fig_risk is not None

    fig_comp = create_comparison_chart(df)
    assert fig_comp is not None

    fig_corr = create_correlation_heatmap(df)
    assert fig_corr is not None
