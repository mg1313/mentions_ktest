import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from mentions_sports_poller.mentions_api.storage import SQLiteStore
from mentions_sports_poller.mentions_api.time_utils import to_utc_iso, utc_now
from mentions_sports_poller.mentions_api.types import DiscoveredMarket, OrderbookLevel, SIDE_YES_BID


def test_idempotent_persistence_on_retry() -> None:
    db_path = Path(f"tasks/test_idempotent_{uuid4().hex}.sqlite")

    store = SQLiteStore(str(db_path))
    store.create_schema()

    now = utc_now()
    ts_utc = to_utc_iso(now)
    market = DiscoveredMarket(
        ticker="KXVALIDMENTION-26FEB10ABCDEF-TEST",
        series_ticker="KXVALIDMENTION",
        title="Market",
        category="Mentions",
        tags=("Sports",),
        status="active",
        close_time_utc=now + timedelta(hours=2),
        created_time_utc=now,
        last_trade_price=0.65,
        volume=12,
        open_interest=14,
        raw_market={"ticker": "KXVALIDMENTION-26FEB10ABCDEF-TEST"},
    )
    store.upsert_market_meta([market])

    levels = [
        OrderbookLevel(side=SIDE_YES_BID, price=0.65, contracts=10, level_rank=0),
        OrderbookLevel(side=SIDE_YES_BID, price=0.64, contracts=10, level_rank=1),
    ]
    metrics = {
        "buy_yes_vwap_25": 0.66,
        "buy_yes_vwap_50": None,
        "buy_yes_vwap_100": None,
        "sell_yes_vwap_25": 0.64,
        "sell_yes_vwap_50": None,
        "sell_yes_vwap_100": None,
        "buy_no_vwap_25": 0.35,
        "sell_no_vwap_25": 0.34,
        "top_spread_yes": 0.02,
        "top_spread_no": 0.02,
        "reason_flags_json": "{\"buy_yes_vwap_50\":\"INSUFFICIENT_DEPTH\"}",
    }

    store.persist_market_poll(
        ts_utc=ts_utc,
        market=market,
        raw_orderbook_json='{"orderbook":{"yes":[[65,10]]}}',
        levels=levels,
        metrics_row=metrics,
    )
    store.persist_market_poll(
        ts_utc=ts_utc,
        market=market,
        raw_orderbook_json='{"orderbook":{"yes":[[65,10]]}}',
        levels=levels,
        metrics_row=metrics,
    )

    conn = sqlite3.connect(db_path)
    snapshot_count = conn.execute("SELECT COUNT(*) FROM orderbook_snapshot").fetchone()[0]
    level_count = conn.execute("SELECT COUNT(*) FROM orderbook_levels").fetchone()[0]
    metrics_count = conn.execute("SELECT COUNT(*) FROM liquidity_metrics").fetchone()[0]
    conn.close()

    assert snapshot_count == 1
    assert level_count == 2
    assert metrics_count == 1
