from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

SIDE_YES_BID = "YES_BID"
SIDE_YES_ASK = "YES_ASK"
SIDE_NO_BID = "NO_BID"
SIDE_NO_ASK = "NO_ASK"
ORDERBOOK_SIDES = (SIDE_YES_BID, SIDE_YES_ASK, SIDE_NO_BID, SIDE_NO_ASK)


@dataclass(frozen=True)
class DiscoveredMarket:
    ticker: str
    series_ticker: str
    title: str
    category: str
    tags: tuple[str, ...]
    status: str
    close_time_utc: datetime | None
    created_time_utc: datetime | None
    last_trade_price: float | None
    volume: int | None
    open_interest: int | None
    raw_market: dict[str, Any]


@dataclass(frozen=True)
class OrderbookLevel:
    side: str
    price: float
    contracts: int
    level_rank: int
