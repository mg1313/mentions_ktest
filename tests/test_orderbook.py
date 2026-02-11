import pytest

from mentions_sports_poller.mentions_api.orderbook import normalize_orderbook
from mentions_sports_poller.mentions_api.types import SIDE_NO_ASK, SIDE_NO_BID, SIDE_YES_ASK, SIDE_YES_BID


def test_normalize_orderbook_derives_asks_from_complement() -> None:
    payload = {
        "yes": [[90, 100], [80, 50]],
        "no": [[8, 75], [5, 20]],
    }
    levels = normalize_orderbook(
        orderbook_payload=payload,
        depth_levels_limit=20,
        depth_target_notional_dollars=1000.0,
    )
    assert levels[SIDE_YES_BID][0].price == 0.90
    assert levels[SIDE_NO_BID][0].price == 0.08
    assert levels[SIDE_YES_ASK][0].price == 0.92
    assert levels[SIDE_NO_ASK][0].price == pytest.approx(0.10)


def test_normalize_orderbook_applies_depth_truncation() -> None:
    payload = {"yes": [[50, 100], [49, 100], [48, 100]], "no": [[50, 100], [49, 100], [48, 100]]}
    levels = normalize_orderbook(
        orderbook_payload=payload,
        depth_levels_limit=2,
        depth_target_notional_dollars=1000.0,
    )
    assert len(levels[SIDE_YES_BID]) == 2
    assert len(levels[SIDE_NO_BID]) == 2
