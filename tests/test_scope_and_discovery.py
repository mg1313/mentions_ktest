from datetime import timedelta

from mentions_sports_poller.mentions_api.discovery import discover_open_mentions_sports_markets, select_active_tickers
from mentions_sports_poller.mentions_api.scope import validate_market_scope
from mentions_sports_poller.mentions_api.time_utils import utc_now
from mentions_sports_poller.mentions_api.types import DiscoveredMarket


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
                "title": "What will the announcers say during Team A vs Team B Professional Basketball Game?",
                "subtitle": "Will ABC be mentioned?",
                "yes_sub_title": "Mentioned",
                "no_sub_title": "Not mentioned",
                "status": "active",
                "close_time": "2026-02-11T05:00:00Z",
                "created_time": "2026-02-10T00:00:00Z",
                "last_price": 55,
                "volume": 10,
                "open_interest": 20,
            },
            {
                "ticker": "KXVALIDMENTION-26FEB10ABCDEF-OTHER",
                "title": "What will the announcers say during Team A vs Team B Professional Football Game?",
                "subtitle": "Will DEF be mentioned?",
                "yes_sub_title": "Mentioned",
                "no_sub_title": "Not mentioned",
                "status": "active",
                "close_time": "2026-02-11T05:00:00Z",
                "created_time": "2026-02-10T00:00:00Z",
                "last_price": 45,
                "volume": 5,
                "open_interest": 8,
            },
            {
                "ticker": "KXOTHER-26FEB10BAD-TEST",
                "title": "Out of scope market",
                "subtitle": "Out of scope subtitle",
                "yes_sub_title": "Yes",
                "no_sub_title": "No",
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
    assert discovered[0].subtitle == "Will ABC be mentioned?"
    assert discovered[0].yes_sub_title == "Mentioned"
    assert discovered[0].no_sub_title == "Not mentioned"


def test_discovery_title_filter_can_be_disabled() -> None:
    discovered = discover_open_mentions_sports_markets(
        FakeClient(),
        required_title_substring="",
    )
    assert {market.ticker for market in discovered} == {
        "KXVALIDMENTION-26FEB10ABCDEF-TEST",
        "KXVALIDMENTION-26FEB10ABCDEF-OTHER",
    }


def test_active_set_filtering_rules() -> None:
    now = utc_now()
    markets = [
        DiscoveredMarket(
            ticker="SOON",
            series_ticker="KXVALIDMENTION",
            title="closes soon",
            subtitle=None,
            yes_sub_title=None,
            no_sub_title=None,
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
            subtitle=None,
            yes_sub_title=None,
            no_sub_title=None,
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
            subtitle=None,
            yes_sub_title=None,
            no_sub_title=None,
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
