from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None and raw != "" else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None and raw != "" else default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return raw if raw is not None and raw != "" else default


def _env_pinned_tickers(name: str = "PINNED_TICKERS") -> set[str]:
    raw = os.getenv(name, "")
    values = [token.strip() for token in raw.split(",")]
    return {value for value in values if value}


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    db_path: str
    request_timeout_seconds: float
    max_retries: int
    backoff_base_seconds: float
    rate_limit_per_second: int
    poll_interval_seconds: int
    poll_jitter_seconds: int
    universe_refresh_seconds: int
    active_close_within_hours: int
    depth_levels_limit: int
    depth_target_notional_dollars: float
    pinned_tickers: set[str]
    vwap_budgets_dollars: tuple[float, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_base_url=_env_str(
                "KALSHI_API_BASE_URL",
                "https://api.elections.kalshi.com/trade-api/v2",
            ),
            db_path=_env_str("SQLITE_DB_PATH", "data/mentions_sports.db"),
            request_timeout_seconds=_env_float("REQUEST_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("MAX_RETRIES", 4),
            backoff_base_seconds=_env_float("BACKOFF_BASE_SECONDS", 0.4),
            rate_limit_per_second=_env_int("RATE_LIMIT_PER_SECOND", 20),
            poll_interval_seconds=_env_int("POLL_INTERVAL_SECONDS", 180),
            poll_jitter_seconds=_env_int("POLL_JITTER_SECONDS", 8),
            universe_refresh_seconds=_env_int("UNIVERSE_REFRESH_SECONDS", 900),
            active_close_within_hours=_env_int("ACTIVE_CLOSE_WITHIN_HOURS", 72),
            depth_levels_limit=_env_int("DEPTH_LEVELS_LIMIT", 20),
            depth_target_notional_dollars=_env_float(
                "DEPTH_TARGET_NOTIONAL_DOLLARS",
                150.0,
            ),
            pinned_tickers=_env_pinned_tickers(),
            vwap_budgets_dollars=(25.0, 50.0, 100.0),
        )
