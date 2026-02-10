from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .scope import is_series_in_scope, validate_market_scope
from .time_utils import parse_utc
from .types import DiscoveredMarket


def discover_open_mentions_sports_markets(
    client: Any,
    logger: logging.Logger | None = None,
) -> list[DiscoveredMarket]:
    log = logger or logging.getLogger(__name__)
    series_rows = client.list_mentions_sports_series()
    in_scope_series: dict[str, dict[str, Any]] = {}

    for series in series_rows:
        series_ticker = series.get("ticker")
        if not series_ticker:
            log.warning("skipping series with missing ticker", extra={"series": series})
            continue
        if not is_series_in_scope(series):
            log.warning("skipping out-of-scope series", extra={"series_ticker": series_ticker})
            continue
        in_scope_series[series_ticker] = series

    discovered: list[DiscoveredMarket] = []
    for series_ticker, series in in_scope_series.items():
        markets = client.list_open_markets(series_ticker)
        for market in markets:
            ok, reason = validate_market_scope(
                market=market,
                source_series_ticker=series_ticker,
                in_scope_series_tickers=set(in_scope_series.keys()),
            )
            if not ok:
                log.warning(
                    "skipping market failing scope assertion",
                    extra={
                        "ticker": market.get("ticker"),
                        "series_ticker": series_ticker,
                        "reason": reason,
                    },
                )
                continue

            discovered.append(
                DiscoveredMarket(
                    ticker=market["ticker"],
                    series_ticker=series_ticker,
                    title=market.get("title") or "",
                    category=series.get("category") or "Mentions",
                    tags=tuple(series.get("tags") or ("Sports",)),
                    status=market.get("status") or "",
                    close_time_utc=parse_utc(market.get("close_time")),
                    created_time_utc=parse_utc(market.get("created_time")),
                    last_trade_price=_extract_last_trade_price(market),
                    volume=_to_int(market.get("volume")),
                    open_interest=_to_int(market.get("open_interest")),
                    raw_market=market,
                )
            )

    return discovered


def select_active_tickers(
    markets: list[DiscoveredMarket],
    now_utc: datetime,
    close_within_hours: int,
    pinned_tickers: set[str],
) -> set[str]:
    deadline = now_utc + timedelta(hours=close_within_hours)
    active: set[str] = set()
    for market in markets:
        is_pinned = market.ticker in pinned_tickers
        closes_soon = (
            market.close_time_utc is not None
            and now_utc <= market.close_time_utc <= deadline
        )
        has_activity = (market.volume or 0) > 0 or (market.open_interest or 0) > 0
        if is_pinned or closes_soon or has_activity:
            active.add(market.ticker)
    return active


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_last_trade_price(market: dict[str, Any]) -> float | None:
    if market.get("last_price_dollars") is not None:
        try:
            return float(market["last_price_dollars"])
        except (TypeError, ValueError):
            return None
    if market.get("last_price") is not None:
        try:
            return float(market["last_price"]) / 100.0
        except (TypeError, ValueError):
            return None
    return None
