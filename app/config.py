"""Configuration and structured logging module with secret masking."""

import logging
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(override=False)

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    alpha_vantage_api_key: str = Field(
        default="demo",
        alias="ALPHA_VANTAGE_API_KEY",
        description="Alpha Vantage API key",
    )
    alpha_vantage_rate_limit_pause: float = Field(
        default=12.0,
        alias="ALPHA_VANTAGE_RATE_LIMIT_PAUSE",
        description="Seconds to sleep between calls to respect free tier rate limit",
    )
    alpha_vantage_daily_max_requests: int = Field(
        default=25,
        alias="ALPHA_VANTAGE_DAILY_MAX_REQUESTS",
        description="Safety threshold for daily API call budget",
    )

    storage_mode: str = Field(
        default="auto",
        alias="STORAGE_MODE",
        description="Storage mode: 'auto', 'bigquery', or 'local'",
    )
    local_data_dir: Path = Field(
        default=BASE_DIR / "data",
        alias="LOCAL_DATA_DIR",
        description="Local directory for SQLite and Parquet files",
    )

    gcp_project_id: str | None = Field(
        default=None,
        alias="GCP_PROJECT_ID",
        description="GCP Project ID for BigQuery",
    )
    bigquery_dataset: str = Field(
        default="market_data",
        alias="BIGQUERY_DATASET",
        description="BigQuery dataset name",
    )
    bigquery_location: str = Field(
        default="US",
        alias="BIGQUERY_LOCATION",
        description="BigQuery dataset geographic location",
    )
    google_application_credentials: str | None = Field(
        default=None,
        alias="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to GCP Service Account JSON credentials file",
    )

    default_timezone: str = Field(
        default="America/Sao_Paulo",
        alias="DEFAULT_TIMEZONE",
        description="Target timezone for normalized timestamps",
    )
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging level",
    )

    default_equities: list[str] = ["PETR4.SAO", "VALE", "AAPL", "MSFT"]
    default_forex: list[str] = ["USD/BRL"]
    default_crypto: list[str] = ["BTC"]

    @property
    def all_default_symbols(self) -> list[str]:
        """Returns consolidated list of monitored asset symbols."""
        return self.default_equities + self.default_forex + self.default_crypto

    @property
    def is_bigquery_configured(self) -> bool:
        """Determines if BigQuery has required configuration parameters."""
        if not self.gcp_project_id:
            return False
        if self.google_application_credentials and not Path(self.google_application_credentials).exists():
            return False
        return True


settings = Settings()


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs API keys and secret tokens from all logs."""

    def __init__(self, secrets_to_mask: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = [s for s in (secrets_to_mask or []) if s and len(s) > 4]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._mask_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._mask_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._mask_value(v) for v in record.args)
        return True

    def _mask_text(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, f"***{secret[-4:]}")
        text = re.sub(r"(apikey=)([a-zA-Z0-9_-]+)", r"\1***REDACTED***", text, flags=re.IGNORECASE)
        text = re.sub(
            r"(API_KEY=)([a-zA-Z0-9_-]+)",
            r"\1***REDACTED***",
            text,
            flags=re.IGNORECASE,
        )
        return text

    def _mask_value(self, val: object) -> object:
        if isinstance(val, str):
            return self._mask_text(val)
        return val


def setup_logging(level: str | None = None) -> logging.Logger:
    """Configures structured console logging with secret masking.

    Args:
        level: Optional log level string.

    Returns:
        Configured logger instance.
    """
    log_level = getattr(logging, (level or settings.log_level).upper(), logging.INFO)
    logger = logging.getLogger("market_pipeline")
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    mask_filter = SensitiveDataFilter(secrets_to_mask=[settings.alpha_vantage_api_key])
    logger.addFilter(mask_filter)
    for h in logger.handlers:
        h.addFilter(mask_filter)

    return logger


logger = setup_logging()
