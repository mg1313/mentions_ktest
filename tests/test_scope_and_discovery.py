from datetime import timedelta

from mentions_sports_poller.discovery import discover_open_mentions_sports_markets, select_active_tickers
from mentions_sports_poller.scope import validate_market_scope
from mentions_sports_poller.time_utils import utc_now
from mentions_sports_poller.types import DiscoveredMarket


class FakeClient:
    def list_mentions_sports_series(self) -> list[dict]:
        return [
            {"ticker": "KXVALIDMENTION", "category": "Mentions", "tags": ["Sports"]},
            {"ticker": "KXPOLIMENTION", "category": "Mentions", "tags": ["Politics"]},
        ]

    def list_open_markets(self, series_ticker: str) -> list[dict]:
        if series_ticker != "KXVALIDMENTION":
            return []
        return [
            {
                "ticker": "KXVALIDMENTION-26FEB10ABCDEF-TEST",
                "title": "Valid test market",
                "status": "active",
                "close_time": "2026-02-11T05:00:00Z",
                "created_time": "2026-02-10T00:00:00Z",
                "last_price": 55,
                "volume": 10,
                "open_interest": 20,
            },
            {
                "ticker": "KXOTHER-26FEB10BAD-TEST",
                "title": "Out of scope market",
                "status": "active",
                "close_time": "2026-02-11T05:00:00Z",
                "created_time": "2026-02-10T00:00:00Z",
                "last_price": 55,
                "volume": 10,
                "open_interest": 20,
            },
        ]


def test_validate_market_scope_rejects_bad_ticker_prefix() -> None:
    ok, reason = validate_market_scope(
        market={"ticker": "KXOTHER-TEST"},
        source_series_ticker="KXVALIDMENTION",
        in_scope_series_tickers={"KXVALIDMENTION"},
    )
    assert not ok
    assert reason == "TICKER_PREFIX_MISMATCH"


def test_discovery_selects_only_mentions_sports_markets() -> None:
    discovered = discover_open_mentions_sports_markets(FakeClient())
    assert len(discovered) == 1
    assert discovered[0].ticker == "KXVALIDMENTION-26FEB10ABCDEF-TEST"
    assert discovered[0].category == "Mentions"
    assert "Sports" in discovered[0].tags


def test_active_set_filtering_rules() -> None:
    now = utc_now()
    markets = [
        DiscoveredMarket(
            ticker="SOON",
            series_ticker="KXVALIDMENTION",
            title="closes soon",
            category="Mentions",
            tags=("Sports",),
            status="active",
            close_time_utc=now + timedelta(hours=1),
            created_time_utc=now,
            last_trade_price=0.5,
            volume=0,
            open_interest=0,
            raw_market={},
        ),
        DiscoveredMarket(
            ticker="ACTIVE_VOLUME",
            series_ticker="KXVALIDMENTION",
            title="has volume",
            category="Mentions",
            tags=("Sports",),
            status="active",
            close_time_utc=now + timedelta(days=10),
            created_time_utc=now,
            last_trade_price=0.5,
            volume=1,
            open_interest=0,
            raw_market={},
        ),
        DiscoveredMarket(
            ticker="PINNED",
            series_ticker="KXVALIDMENTION",
            title="pinned",
            category="Mentions",
            tags=("Sports",),
            status="active",
            close_time_utc=now + timedelta(days=10),
            created_time_utc=now,
            last_trade_price=0.5,
            volume=0,
            open_interest=0,
            raw_market={},
        ),
    ]
    active = select_active_tickers(
        markets=markets,
        now_utc=now,
        close_within_hours=72,
        pinned_tickers={"PINNED"},
    )
    assert active == {"SOON", "ACTIVE_VOLUME", "PINNED"}
