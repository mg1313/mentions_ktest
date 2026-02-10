from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .types import ORDERBOOK_SIDES, OrderbookLevel, SIDE_NO_ASK, SIDE_NO_BID, SIDE_YES_ASK, SIDE_YES_BID


def normalize_orderbook(
    orderbook_payload: dict[str, Any],
    depth_levels_limit: int,
    depth_target_notional_dollars: float,
) -> dict[str, list[OrderbookLevel]]:
    yes_bids = _parse_bid_side(orderbook_payload.get("yes"))
    no_bids = _parse_bid_side(orderbook_payload.get("no"))

    levels_by_side: dict[str, list[OrderbookLevel]] = {
        SIDE_YES_BID: _rank_levels(_truncate_levels(yes_bids, depth_levels_limit, depth_target_notional_dollars), SIDE_YES_BID),
        SIDE_NO_BID: _rank_levels(_truncate_levels(no_bids, depth_levels_limit, depth_target_notional_dollars), SIDE_NO_BID),
        SIDE_YES_ASK: _rank_levels(
            _truncate_levels(_derive_asks_from_complement(no_bids), depth_levels_limit, depth_target_notional_dollars),
            SIDE_YES_ASK,
        ),
        SIDE_NO_ASK: _rank_levels(
            _truncate_levels(_derive_asks_from_complement(yes_bids), depth_levels_limit, depth_target_notional_dollars),
            SIDE_NO_ASK,
        ),
    }
    for side in ORDERBOOK_SIDES:
        levels_by_side.setdefault(side, [])
    return levels_by_side


def best_price(levels: Sequence[OrderbookLevel]) -> float | None:
    return levels[0].price if levels else None


def _parse_bid_side(raw_levels: Any) -> list[tuple[float, int]]:
    parsed: list[tuple[float, int]] = []
    if not isinstance(raw_levels, list):
        return parsed
    for level in raw_levels:
        if not isinstance(level, list) and not isinstance(level, tuple):
            continue
        if len(level) < 2:
            continue
        try:
            price_cents = int(level[0])
            contracts = int(level[1])
        except (TypeError, ValueError):
            continue
        if contracts <= 0 or price_cents < 0 or price_cents > 100:
            continue
        parsed.append((price_cents / 100.0, contracts))
    parsed.sort(key=lambda item: item[0], reverse=True)
    return parsed


def _derive_asks_from_complement(bid_levels: list[tuple[float, int]]) -> list[tuple[float, int]]:
    derived: list[tuple[float, int]] = []
    for bid_price, contracts in bid_levels:
        bid_cents = int(round(bid_price * 100))
        ask_cents = 100 - bid_cents
        derived.append((ask_cents / 100.0, contracts))
    derived = [level for level in derived if 0.0 <= level[0] <= 1.0]
    derived.sort(key=lambda item: item[0])
    return derived


def _truncate_levels(
    levels: list[tuple[float, int]],
    depth_levels_limit: int,
    depth_target_notional_dollars: float,
) -> list[tuple[float, int]]:
    truncated: list[tuple[float, int]] = []
    cumulative_notional = 0.0
    for price, contracts in levels:
        if len(truncated) >= depth_levels_limit:
            break
        truncated.append((price, contracts))
        cumulative_notional += price * contracts
        if cumulative_notional >= depth_target_notional_dollars:
            break
    return truncated


def _rank_levels(levels: list[tuple[float, int]], side: str) -> list[OrderbookLevel]:
    return [
        OrderbookLevel(side=side, price=price, contracts=contracts, level_rank=rank)
        for rank, (price, contracts) in enumerate(levels)
    ]
