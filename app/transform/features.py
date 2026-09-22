"""Feature engineering module: technical indicators and financial risk metrics."""

import numpy as np
import pandas as pd

from app.schemas.features import DailyFeatures
from app.schemas.timeseries import DailyBarClean


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Wilder's Relative Strength Index (RSI).

    Args:
        series: Price series of close values.
        period: Lookback window for smoothing.

    Returns:
        Series of bounded RSI values [0.0, 100.0].
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.fillna(50.0)
    return rsi.round(4)


def calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Calculates Moving Average Convergence Divergence (MACD).

    Args:
        series: Price series of close values.
        fast: Fast exponential moving average period.
        slow: Slow exponential moving average period.
        signal: Signal line smoothing period.

    Returns:
        DataFrame containing macd_line, macd_signal, and macd_hist columns.
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    return pd.DataFrame(
        {
            "macd_line": macd_line.round(4),
            "macd_signal": macd_signal.round(4),
            "macd_hist": macd_hist.round(4),
        }
    )


def enrich_timeseries_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical indicators and risk metrics across grouped asset series.

    Args:
        df: Input DataFrame containing symbol, date, open, high, low, close, volume.

    Returns:
        DataFrame enriched with moving averages, RSI, MACD, volatility, and drawdown.
    """
    if df.empty:
        return df

    df = df.sort_values(by=["symbol", "date"]).reset_index(drop=True)
    enriched_groups = []

    for _, group in df.groupby("symbol"):
        g = group.copy()
        close = g["close"].astype(float)
        vol = g["volume"].astype(float)

        g["daily_return_pct"] = (close.pct_change() * 100.0).round(4)
        g["volatility_21d"] = (g["daily_return_pct"].rolling(window=21, min_periods=5).std() * np.sqrt(252)).round(4)
        g["volume_avg_21d"] = vol.rolling(window=21, min_periods=1).mean().round(0)

        rolling_max = close.rolling(window=252, min_periods=1).max()
        g["max_drawdown_252d"] = ((rolling_max - close) / rolling_max * 100.0).round(4)

        g["sma_7"] = close.rolling(window=7, min_periods=1).mean().round(4)
        g["sma_21"] = close.rolling(window=21, min_periods=1).mean().round(4)
        g["sma_50"] = close.rolling(window=50, min_periods=1).mean().round(4)

        g["rsi_14"] = calculate_rsi(close, period=14)
        macd_df = calculate_macd(close, fast=12, slow=26, signal=9)
        g["macd_line"] = macd_df["macd_line"]
        g["macd_signal"] = macd_df["macd_signal"]
        g["macd_hist"] = macd_df["macd_hist"]

        enriched_groups.append(g)

    return pd.concat(enriched_groups, ignore_index=True)


def calculate_financial_features(bars: list[DailyBarClean]) -> list[DailyFeatures]:
    """Transforms raw cleaned daily bars into strongly-typed DailyFeatures.

    Args:
        bars: Collection of DailyBarClean instances.

    Returns:
        Collection of computed DailyFeatures instances.
    """
    if not bars:
        return []

    records = [b.to_dict() for b in bars]
    df = pd.DataFrame(records)
    enriched_df = enrich_timeseries_dataframe(df)

    features_list: list[DailyFeatures] = []
    for _, row in enriched_df.iterrows():
        f = DailyFeatures(
            symbol=str(row["symbol"]),
            date=pd.to_datetime(row["date"]).date(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            adjusted_close=float(row["adjusted_close"]) if pd.notnull(row["adjusted_close"]) else None,
            volume=int(row["volume"]),
            daily_return_pct=float(row["daily_return_pct"]) if pd.notnull(row["daily_return_pct"]) else None,
            volatility_21d=float(row["volatility_21d"]) if pd.notnull(row["volatility_21d"]) else None,
            volume_avg_21d=float(row["volume_avg_21d"]) if pd.notnull(row["volume_avg_21d"]) else None,
            max_drawdown_252d=float(row["max_drawdown_252d"]) if pd.notnull(row["max_drawdown_252d"]) else None,
            sma_7=float(row["sma_7"]) if pd.notnull(row["sma_7"]) else None,
            sma_21=float(row["sma_21"]) if pd.notnull(row["sma_21"]) else None,
            sma_50=float(row["sma_50"]) if pd.notnull(row["sma_50"]) else None,
            rsi_14=float(row["rsi_14"]) if pd.notnull(row["rsi_14"]) else None,
            macd_line=float(row["macd_line"]) if pd.notnull(row["macd_line"]) else None,
            macd_signal=float(row["macd_signal"]) if pd.notnull(row["macd_signal"]) else None,
            macd_hist=float(row["macd_hist"]) if pd.notnull(row["macd_hist"]) else None,
            ingested_at=pd.to_datetime(row["ingested_at"]).to_pydatetime(),
        )
        features_list.append(f)

    return features_list
