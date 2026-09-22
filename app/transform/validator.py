"""Structural validation and rejection reporting using Pydantic v2."""

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.config import logger
from app.schemas.quote import GlobalQuoteClean
from app.schemas.timeseries import DailyBarClean


@dataclass
class ValidationReport:
    """Summary metrics of record validation process."""

    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    error_messages: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.invalid_records == 0 and self.valid_records > 0


def validate_quote(
    raw_dict: dict[str, Any],
) -> tuple[GlobalQuoteClean | None, ValidationReport]:
    """Validates quote dictionary against Pydantic schema."""
    report = ValidationReport(total_records=1)
    try:
        quote = GlobalQuoteClean.model_validate(raw_dict)
        report.valid_records = 1
        return quote, report
    except ValidationError as exc:
        report.invalid_records = 1
        err_str = f"Quote validation error: {exc}"
        report.error_messages.append(err_str)
        logger.warning(err_str)
        return None, report


def validate_daily_bars(
    bars: list[DailyBarClean],
) -> tuple[list[DailyBarClean], ValidationReport]:
    """Validates a collection of daily bars and isolates anomalies."""
    report = ValidationReport(total_records=len(bars))
    valid_bars: list[DailyBarClean] = []

    for bar in bars:
        try:
            # Re-validate with Pydantic model
            validated = DailyBarClean.model_validate(bar)
            valid_bars.append(validated)
            report.valid_records += 1
        except ValidationError as exc:
            report.invalid_records += 1
            err_msg = f"Validation failed for {bar.symbol} on {bar.date}: {exc}"
            report.error_messages.append(err_msg)
            logger.warning(err_msg)

    return valid_bars, report
