from __future__ import annotations

from typing import Any

REQUIRED_CATEGORY = "Mentions"
REQUIRED_TAG = "Sports"


def is_series_in_scope(series: dict[str, Any]) -> bool:
    category = series.get("category")
    tags = series.get("tags") or []
    return category == REQUIRED_CATEGORY and REQUIRED_TAG in tags


def validate_market_scope(
    market: dict[str, Any],
    source_series_ticker: str,
    in_scope_series_tickers: set[str],
) -> tuple[bool, str]:
    if source_series_ticker not in in_scope_series_tickers:
        return False, "SERIES_NOT_IN_SCOPE"

    market_series_ticker = market.get("series_ticker")
    if market_series_ticker and market_series_ticker != source_series_ticker:
        return False, "SERIES_TICKER_MISMATCH"

    ticker = market.get("ticker", "")
    if not ticker.startswith(f"{source_series_ticker}-"):
        return False, "TICKER_PREFIX_MISMATCH"

    market_category = market.get("category")
    if market_category is not None and market_category != REQUIRED_CATEGORY:
        return False, "CATEGORY_MISMATCH"

    market_tags = market.get("tags")
    if market_tags is not None and REQUIRED_TAG not in market_tags:
        return False, "TAG_MISMATCH"

    return True, "OK"
