"""Command-line interface for pipeline setup, data ingestion, backfill, and status."""

import argparse
import subprocess
import sys
from datetime import datetime

import pandas as pd
from rich.console import Console
from rich.table import Table

from app.config import logger, settings
from app.extract.alpha_vantage_client import (
    AlphaVantageClient,
    AlphaVantageRateLimitError,
)
from app.extract.rate_limiter import RateLimiter, RateLimitExceededError
from app.load.storage_manager import get_storage_manager
from app.schemas.quote import GlobalQuoteClean
from app.schemas.timeseries import DailyBarClean
from app.transform.cleaner import (
    clean_crypto_data,
    clean_fx_data,
    clean_quote_data,
    clean_timeseries_daily_data,
)
from app.transform.features import calculate_financial_features

console = Console(highlight=False)


def run_setup() -> None:
    """Initializes storage infrastructure and provision schemas."""
    storage = get_storage_manager()
    storage.ensure_setup()

    table = Table(
        title="Storage Configuration",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("storage_mode", settings.storage_mode)
    table.add_row("active_backend", storage.active_backend.upper())
    table.add_row("local_data_dir", str(settings.local_data_dir))
    table.add_row("gcp_project_id", str(settings.gcp_project_id or "local"))
    table.add_row("bigquery_dataset", settings.bigquery_dataset)
    table.add_row("default_timezone", settings.default_timezone)

    console.print(table)
    console.print("Storage infrastructure initialized.")


def parse_target_symbols(symbols_arg: str | None) -> list[str]:
    """Parses symbol arguments into unique uppercase tokens.

    Args:
        symbols_arg: Comma-separated string or 'all'.

    Returns:
        List of unique uppercase ticker strings.
    """
    if not symbols_arg or symbols_arg.lower() in {"all", "default"}:
        return settings.all_default_symbols
    return [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]


def collect_symbol(
    client: AlphaVantageClient,
    symbol: str,
    outputsize: str = "compact",
    force: bool = False,
) -> bool:
    """Executes extraction, medallion transformations, and storage for a symbol.

    Args:
        client: Configured Alpha Vantage client instance.
        symbol: Market ticker symbol.
        outputsize: Time series size ('compact' or 'full').
        force: Bypass daily quota threshold if True.

    Returns:
        True if symbol was processed and persisted successfully, False otherwise.
    """
    storage = get_storage_manager()
    sym = symbol.strip().upper()

    try:
        quote_clean: GlobalQuoteClean | None = None
        cleaned_bars: list[DailyBarClean] = []

        if "/" in sym and not sym.startswith("BTC") and not sym.startswith("ETH"):
            from_curr, to_curr = sym.split("/")
            fx_raw = client.get_fx_daily(from_curr, to_curr, outputsize=outputsize, force=force)
            storage.save_bronze_raw(sym, fx_raw, "FX_DAILY")
            cleaned_bars = clean_fx_data(fx_raw, symbol=sym)

            if cleaned_bars:
                latest = cleaned_bars[-1]
                prev = cleaned_bars[-2] if len(cleaned_bars) > 1 else latest
                chg = latest.close - prev.close
                chg_pct = (chg / prev.close * 100.0) if prev.close else 0.0
                quote_clean = GlobalQuoteClean(
                    symbol=sym,
                    open=latest.open,
                    high=latest.high,
                    low=latest.low,
                    price=latest.close,
                    volume=latest.volume,
                    latest_trading_day=latest.date,
                    previous_close=prev.close,
                    change=chg,
                    change_percent=chg_pct,
                    ingested_at=latest.ingested_at,
                )

        elif sym in {"BTC", "ETH", "BTC/USD", "ETH/USD"}:
            base_sym = sym.split("/")[0]
            crypto_raw = client.get_crypto_daily(base_sym, market="USD", force=force)
            storage.save_bronze_raw(sym, crypto_raw, "DIGITAL_CURRENCY_DAILY")
            cleaned_bars = clean_crypto_data(crypto_raw, symbol=base_sym, market="USD")

            if cleaned_bars:
                latest = cleaned_bars[-1]
                prev = cleaned_bars[-2] if len(cleaned_bars) > 1 else latest
                chg = latest.close - prev.close
                chg_pct = (chg / prev.close * 100.0) if prev.close else 0.0
                quote_clean = GlobalQuoteClean(
                    symbol=sym if "/" in sym else f"{sym}/USD",
                    open=latest.open,
                    high=latest.high,
                    low=latest.low,
                    price=latest.close,
                    volume=latest.volume,
                    latest_trading_day=latest.date,
                    previous_close=prev.close,
                    change=chg,
                    change_percent=chg_pct,
                    ingested_at=latest.ingested_at,
                )

        else:
            try:
                quote_raw = client.get_quote(sym, force=force)
                storage.save_bronze_raw(sym, quote_raw, "GLOBAL_QUOTE")
                quote_clean = clean_quote_data(quote_raw, symbol=sym)
            except Exception as exc:
                logger.warning("quote_fetch_skipped symbol=%s reason=%s", sym, exc)

            ts_raw = client.get_daily_series(sym, outputsize=outputsize, force=force)
            storage.save_bronze_raw(sym, ts_raw, "TIME_SERIES_DAILY")
            cleaned_bars = clean_timeseries_daily_data(ts_raw, symbol=sym)

        if quote_clean:
            storage.save_gold_latest_quote(quote_clean)

        if cleaned_bars:
            storage.save_silver_timeseries(cleaned_bars)
            features = calculate_financial_features(cleaned_bars)
            storage.save_gold_features(features)
            console.print(f"Ingested {sym}: bars={len(cleaned_bars)} latest_price={quote_clean.price if quote_clean else 'N/A'}")
            return True

        console.print(f"No daily bars parsed for {sym}.")
        return False

    except (RateLimitExceededError, AlphaVantageRateLimitError) as rle:
        console.print(f"Rate limit reached for {sym}: {rle}")
        return False
    except Exception as exc:
        console.print(f"Error processing {sym}: {exc}")
        logger.exception("collection_error symbol=%s", sym)
        return False


def run_collect(symbols_arg: str | None = None, force: bool = False) -> None:
    """Runs data collection for target symbols.

    Args:
        symbols_arg: Target symbol list or 'all'.
        force: Bypass safety rate limit if True.
    """
    symbols = parse_target_symbols(symbols_arg)
    console.print(f"Starting ingestion pipeline for: {', '.join(symbols)}")

    client = AlphaVantageClient()
    success_count = sum(1 for sym in symbols if collect_symbol(client, sym, outputsize="compact", force=force))

    console.print(f"Collection completed: {success_count}/{len(symbols)} assets processed.")


def run_backfill(days: int = 365, symbols_arg: str | None = None, force: bool = False) -> None:
    """Executes extended historical time series backfill.

    Args:
        days: Historical days target.
        symbols_arg: Target symbols.
        force: Bypass safety rate limit if True.
    """
    symbols = parse_target_symbols(symbols_arg)
    console.print(f"Starting historical backfill for: {', '.join(symbols)} (target_days={days})")

    client = AlphaVantageClient()
    for sym in symbols:
        collect_symbol(client, sym, outputsize="full", force=force)

    console.print("Backfill completed.")


def run_sync() -> None:
    """Synchronizes local SQLite and Parquet datasets directly to BigQuery."""
    storage = get_storage_manager()
    if not storage.bq_loader:
        console.print("BigQuery loader not configured. Set STORAGE_MODE=bigquery in .env")
        return

    local_silver_df = storage.local_loader.query_dataframe("SELECT * FROM silver_timeseries_daily")
    if not local_silver_df.empty:
        for sym, group in local_silver_df.groupby("symbol"):
            bars = [
                DailyBarClean(
                    symbol=str(row["symbol"]),
                    date=pd.to_datetime(row["date"]).date(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    adjusted_close=float(row["adjusted_close"]),
                    volume=int(row["volume"]),
                    ingested_at=pd.to_datetime(row["ingested_at"]).to_pydatetime() if pd.notnull(row.get("ingested_at")) else datetime.now(),
                )
                for _, row in group.iterrows()
            ]
            count_silver = storage.bq_loader.save_silver_timeseries(bars)
            features = calculate_financial_features(bars)
            count_gold = storage.bq_loader.save_gold_features(features)
            console.print(f"Synced {sym}: silver_bars={count_silver} gold_features={count_gold}")

    local_quotes_df = storage.local_loader.query_dataframe("SELECT * FROM gold_latest_quotes")
    if not local_quotes_df.empty:
        for _, row in local_quotes_df.iterrows():
            quote = GlobalQuoteClean(
                symbol=str(row["symbol"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                price=float(row["price"]),
                volume=int(row["volume"]),
                latest_trading_day=pd.to_datetime(row["latest_trading_day"]).date(),
                previous_close=float(row["previous_close"]),
                change=float(row["change"]),
                change_percent=float(row["change_percent"]),
                ingested_at=pd.to_datetime(row["ingested_at"]).to_pydatetime() if pd.notnull(row.get("ingested_at")) else datetime.now(),
            )
            storage.bq_loader.save_gold_latest_quote(quote)
        console.print(f"Synced gold quotes: count={len(local_quotes_df)}")

    console.print("BigQuery synchronization completed.")


def run_status() -> None:
    """Prints storage record metrics and current API budget status."""
    storage = get_storage_manager()
    status = storage.get_storage_status()
    rate_limiter = RateLimiter()
    quota = rate_limiter.get_quota_state()

    table = Table(title="Storage Metrics", show_header=True, header_style="bold")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="green")

    table.add_row("active_backend", status["backend"].upper())
    table.add_row("silver_daily_bars", str(status["silver_count"]))
    table.add_row("gold_feature_rows", str(status["gold_features_count"]))
    table.add_row("gold_active_quotes", str(status["gold_quotes_count"]))
    table.add_row(
        "monitored_symbols",
        ", ".join(status["symbols_tracked"]) if status["symbols_tracked"] else "none",
    )
    table.add_row("last_ingestion", str(status["last_ingestion"] or "never"))
    console.print(table)

    quota_table = Table(title="API Daily Quota", show_header=True, header_style="bold")
    quota_table.add_column("Date", style="bold")
    quota_table.add_column("Requests Used", style="cyan")
    quota_table.add_column("Daily Limit", style="magenta")
    quota_table.add_column("Remaining Budget", style="green")

    used = quota.get("count", 0)
    limit = settings.alpha_vantage_daily_max_requests
    remaining = max(0, limit - used)
    quota_table.add_row(
        str(quota.get("date", str(datetime.now().date()))),
        str(used),
        str(limit),
        str(remaining),
    )
    console.print(quota_table)


def run_dashboard() -> None:
    """Launches Streamlit dashboard subprocess."""
    console.print("Launching Streamlit dashboard...")
    app_path = settings.local_data_dir.parent / "app" / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    subprocess.run(cmd)


def build_parser() -> argparse.ArgumentParser:
    """Constructs command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Alpha Vantage Financial Market Data Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    subparsers.add_parser("setup", help="Initialize BigQuery datasets/tables or local SQLite")

    collect_parser = subparsers.add_parser("collect", help="Ingest and process market data")
    collect_parser.add_argument("--symbols", type=str, default="all", help="Comma-separated symbols or 'all'")
    collect_parser.add_argument("--force", action="store_true", help="Bypass daily API quota guard")

    backfill_parser = subparsers.add_parser("backfill", help="Historical load with full outputsize")
    backfill_parser.add_argument("--days", type=int, default=365, help="Target historical days")
    backfill_parser.add_argument("--symbols", type=str, default="all", help="Comma-separated symbols or 'all'")
    backfill_parser.add_argument("--force", action="store_true", help="Bypass daily API quota guard")

    subparsers.add_parser("sync", help="Synchronize local storage into BigQuery")
    subparsers.add_parser("status", help="Inspect database row counts and quota status")
    subparsers.add_parser("dashboard", help="Start the Streamlit dashboard")

    return parser


def main() -> None:
    """Entry point for CLI execution."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        run_setup()
    elif args.command == "collect":
        run_collect(symbols_arg=args.symbols, force=args.force)
    elif args.command == "backfill":
        run_backfill(days=args.days, symbols_arg=args.symbols, force=args.force)
    elif args.command == "sync":
        run_sync()
    elif args.command == "status":
        run_status()
    elif args.command == "dashboard":
        run_dashboard()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
