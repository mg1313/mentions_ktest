from __future__ import annotations

import json
from typing import Sequence

from .orderbook import best_price
from .types import OrderbookLevel, SIDE_NO_ASK, SIDE_NO_BID, SIDE_YES_ASK, SIDE_YES_BID

INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"


def compute_budget_vwap(levels: Sequence[OrderbookLevel], budget_dollars: float) -> tuple[float | None, str | None]:
    if budget_dollars <= 0:
        return None, "INVALID_BUDGET"

    remaining_budget = budget_dollars
    contracts_total = 0.0
    notional_total = 0.0

    for level in levels:
        if level.price <= 0 or level.contracts <= 0:
            continue
        level_notional = level.price * level.contracts
        fill_notional = min(remaining_budget, level_notional)
        fill_contracts = fill_notional / level.price

        contracts_total += fill_contracts
        notional_total += fill_notional
        remaining_budget -= fill_notional
        if remaining_budget <= 1e-9:
            break

    if remaining_budget > 1e-9 or contracts_total <= 0:
        return None, INSUFFICIENT_DEPTH

    return notional_total / contracts_total, None


def compute_liquidity_metrics(
    ts_utc: str,
    ticker: str,
    levels_by_side: dict[str, list[OrderbookLevel]],
    budgets_dollars: tuple[float, ...],
) -> dict[str, float | str | None]:
    reasons: dict[str, str] = {}
    yes_bids = levels_by_side.get(SIDE_YES_BID, [])
    yes_asks = levels_by_side.get(SIDE_YES_ASK, [])
    no_bids = levels_by_side.get(SIDE_NO_BID, [])
    no_asks = levels_by_side.get(SIDE_NO_ASK, [])

    budget_25, budget_50, budget_100 = budgets_dollars

    buy_yes_25, buy_yes_25_reason = compute_budget_vwap(yes_asks, budget_25)
    buy_yes_50, buy_yes_50_reason = compute_budget_vwap(yes_asks, budget_50)
    buy_yes_100, buy_yes_100_reason = compute_budget_vwap(yes_asks, budget_100)

    sell_yes_25, sell_yes_25_reason = compute_budget_vwap(yes_bids, budget_25)
    sell_yes_50, sell_yes_50_reason = compute_budget_vwap(yes_bids, budget_50)
    sell_yes_100, sell_yes_100_reason = compute_budget_vwap(yes_bids, budget_100)

    buy_no_25, buy_no_25_reason = compute_budget_vwap(no_asks, budget_25)
    sell_no_25, sell_no_25_reason = compute_budget_vwap(no_bids, budget_25)

    for key, reason in (
        ("buy_yes_vwap_25", buy_yes_25_reason),
        ("buy_yes_vwap_50", buy_yes_50_reason),
        ("buy_yes_vwap_100", buy_yes_100_reason),
        ("sell_yes_vwap_25", sell_yes_25_reason),
        ("sell_yes_vwap_50", sell_yes_50_reason),
        ("sell_yes_vwap_100", sell_yes_100_reason),
        ("buy_no_vwap_25", buy_no_25_reason),
        ("sell_no_vwap_25", sell_no_25_reason),
    ):
        if reason:
            reasons[key] = reason

    best_yes_bid = best_price(yes_bids)
    best_yes_ask = best_price(yes_asks)
    best_no_bid = best_price(no_bids)
    best_no_ask = best_price(no_asks)

    top_spread_yes = (
        best_yes_ask - best_yes_bid
        if best_yes_bid is not None and best_yes_ask is not None
        else None
    )
    top_spread_no = (
        best_no_ask - best_no_bid
        if best_no_bid is not None and best_no_ask is not None
        else None
    )

    return {
        "ts_utc": ts_utc,
        "ticker": ticker,
        "buy_yes_vwap_25": buy_yes_25,
        "buy_yes_vwap_50": buy_yes_50,
        "buy_yes_vwap_100": buy_yes_100,
        "sell_yes_vwap_25": sell_yes_25,
        "sell_yes_vwap_50": sell_yes_50,
        "sell_yes_vwap_100": sell_yes_100,
        "buy_no_vwap_25": buy_no_25,
        "sell_no_vwap_25": sell_no_25,
        "top_spread_yes": top_spread_yes,
        "top_spread_no": top_spread_no,
        "reason_flags_json": json.dumps(reasons, separators=(",", ":"), sort_keys=True) if reasons else None,
    }
