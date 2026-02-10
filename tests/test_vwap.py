from mentions_sports_poller.types import OrderbookLevel, SIDE_YES_ASK
from mentions_sports_poller.vwap import INSUFFICIENT_DEPTH, compute_budget_vwap


def _levels(data: list[tuple[float, int]]) -> list[OrderbookLevel]:
    return [
        OrderbookLevel(side=SIDE_YES_ASK, price=price, contracts=contracts, level_rank=index)
        for index, (price, contracts) in enumerate(data)
    ]


def test_vwap_exact_fill() -> None:
    vwap, reason = compute_budget_vwap(_levels([(0.50, 50)]), budget_dollars=25.0)
    assert reason is None
    assert vwap == 0.50


def test_vwap_partial_final_level() -> None:
    vwap, reason = compute_budget_vwap(_levels([(0.80, 20), (0.85, 10)]), budget_dollars=20.0)
    assert reason is None
    assert vwap == 20.0 / (20.0 + (4.0 / 0.85))


def test_vwap_insufficient_depth() -> None:
    vwap, reason = compute_budget_vwap(_levels([(0.80, 20), (0.85, 10)]), budget_dollars=25.0)
    assert vwap is None
    assert reason == INSUFFICIENT_DEPTH
