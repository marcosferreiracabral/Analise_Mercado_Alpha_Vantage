"""Rate limiting and daily API quota management for Alpha Vantage."""

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from app.config import logger, settings


class RateLimitExceededError(Exception):
    """Exception raised when API call frequency or daily budget is exceeded."""


class RateLimiter:
    """Manages inter-request pauses and tracks 25 req/day free tier budget."""

    def __init__(
        self,
        pause_seconds: float | None = None,
        daily_max_requests: int | None = None,
        quota_file: Path | None = None,
    ) -> None:
        self.pause_seconds = pause_seconds if pause_seconds is not None else settings.alpha_vantage_rate_limit_pause
        self.daily_max_requests = (
            daily_max_requests if daily_max_requests is not None else settings.alpha_vantage_daily_max_requests
        )
        self.quota_file = quota_file or (settings.local_data_dir / ".daily_quota.json")
        self._last_request_time: float = 0.0

    def _ensure_quota_dir(self) -> None:
        self.quota_file.parent.mkdir(parents=True, exist_ok=True)

    def get_quota_state(self) -> dict[str, Any]:
        """Loads and returns the current daily request count for today."""
        today_str = date.today().isoformat()
        if not self.quota_file.exists():
            return {"date": today_str, "count": 0}

        try:
            with open(self.quota_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("date") == today_str:
                    return {"date": today_str, "count": int(data.get("count", 0))}
        except Exception as e:
            logger.warning("Failed reading quota tracker file %s: %s", self.quota_file, e)

        return {"date": today_str, "count": 0}

    def _save_quota_state(self, state: dict[str, Any]) -> None:
        """Persists today's updated request count."""
        try:
            self._ensure_quota_dir()
            with open(self.quota_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning("Failed saving quota tracker file %s: %s", self.quota_file, e)

    def check_and_throttle(self, force: bool = False) -> int:
        """Enforces inter-request pause and checks daily request quota budget.

        Args:
            force: If True, allows proceeding even if daily quota is exceeded.

        Returns:
            The new request count for today.
        """
        state = self.get_quota_state()
        count = state["count"]

        if count >= self.daily_max_requests and not force:
            raise RateLimitExceededError(
                f"Alpha Vantage daily limit reached ({count}/{self.daily_max_requests} calls used today). "
                "Use --force to bypass safety limit if using a premium key or offline fixtures."
            )

        # Enforce rate limit pause between sequential requests
        now = time.time()
        elapsed = now - self._last_request_time
        if self._last_request_time > 0 and elapsed < self.pause_seconds:
            sleep_duration = self.pause_seconds - elapsed
            logger.debug(
                "Rate limit pause: sleeping %.2f seconds (pause=%.1fs)...",
                sleep_duration,
                self.pause_seconds,
            )
            time.sleep(sleep_duration)

        # Update timestamps and persistent count
        self._last_request_time = time.time()
        new_count = count + 1
        self._save_quota_state({"date": date.today().isoformat(), "count": new_count})
        logger.info(
            "API Request dispatched (Today's quota: %d/%d used)",
            new_count,
            self.daily_max_requests,
        )
        return new_count

    def reset_quota(self) -> None:
        """Resets the daily quota tracker for today (useful for testing)."""
        self._save_quota_state({"date": date.today().isoformat(), "count": 0})
