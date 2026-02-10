from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .time_utils import to_utc_iso
from .types import DiscoveredMarket, OrderbookLevel


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_meta (
                    ticker TEXT PRIMARY KEY,
                    series_ticker TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    status TEXT NOT NULL,
                    close_time_utc TEXT,
                    created_time_utc TEXT
                );

                CREATE TABLE IF NOT EXISTS orderbook_snapshot (
                    ts_utc TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    last_trade_price REAL,
                    volume INTEGER,
                    open_interest INTEGER,
                    raw_orderbook_json TEXT,
                    PRIMARY KEY (ts_utc, ticker)
                );

                CREATE TABLE IF NOT EXISTS orderbook_levels (
                    ts_utc TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('YES_BID','YES_ASK','NO_BID','NO_ASK')),
                    price REAL NOT NULL,
                    contracts INTEGER NOT NULL,
                    level_rank INTEGER NOT NULL,
                    PRIMARY KEY (ts_utc, ticker, side, level_rank)
                );

                CREATE TABLE IF NOT EXISTS liquidity_metrics (
                    ts_utc TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    buy_yes_vwap_25 REAL,
                    buy_yes_vwap_50 REAL,
                    buy_yes_vwap_100 REAL,
                    sell_yes_vwap_25 REAL,
                    sell_yes_vwap_50 REAL,
                    sell_yes_vwap_100 REAL,
                    buy_no_vwap_25 REAL,
                    sell_no_vwap_25 REAL,
                    top_spread_yes REAL,
                    top_spread_no REAL,
                    reason_flags_json TEXT,
                    PRIMARY KEY (ts_utc, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_snapshot_ticker_ts
                    ON orderbook_snapshot (ticker, ts_utc);
                CREATE INDEX IF NOT EXISTS idx_snapshot_ts
                    ON orderbook_snapshot (ts_utc);
                CREATE INDEX IF NOT EXISTS idx_levels_ticker_ts
                    ON orderbook_levels (ticker, ts_utc);
                CREATE INDEX IF NOT EXISTS idx_levels_ts
                    ON orderbook_levels (ts_utc);
                CREATE INDEX IF NOT EXISTS idx_levels_ticker_side_rank
                    ON orderbook_levels (ticker, side, level_rank);
                """
            )

    def upsert_market_meta(self, markets: Iterable[DiscoveredMarket]) -> None:
        rows = [
            (
                market.ticker,
                market.series_ticker,
                market.title,
                market.category,
                json.dumps(market.tags, separators=(",", ":")),
                market.status,
                to_utc_iso(market.close_time_utc) if market.close_time_utc else None,
                to_utc_iso(market.created_time_utc) if market.created_time_utc else None,
            )
            for market in markets
        ]
        if not rows:
            return

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO market_meta (
                    ticker, series_ticker, title, category, tags, status, close_time_utc, created_time_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    series_ticker=excluded.series_ticker,
                    title=excluded.title,
                    category=excluded.category,
                    tags=excluded.tags,
                    status=excluded.status,
                    close_time_utc=excluded.close_time_utc,
                    created_time_utc=excluded.created_time_utc
                """,
                rows,
            )

    def persist_market_poll(
        self,
        ts_utc: str,
        market: DiscoveredMarket,
        raw_orderbook_json: str,
        levels: list[OrderbookLevel],
        metrics_row: dict[str, float | str | None],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orderbook_snapshot (
                    ts_utc, ticker, last_trade_price, volume, open_interest, raw_orderbook_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts_utc, ticker) DO UPDATE SET
                    last_trade_price=excluded.last_trade_price,
                    volume=excluded.volume,
                    open_interest=excluded.open_interest,
                    raw_orderbook_json=excluded.raw_orderbook_json
                """,
                (
                    ts_utc,
                    market.ticker,
                    market.last_trade_price,
                    market.volume,
                    market.open_interest,
                    raw_orderbook_json,
                ),
            )

            conn.executemany(
                """
                INSERT INTO orderbook_levels (
                    ts_utc, ticker, side, price, contracts, level_rank
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts_utc, ticker, side, level_rank) DO UPDATE SET
                    price=excluded.price,
                    contracts=excluded.contracts
                """,
                [
                    (
                        ts_utc,
                        market.ticker,
                        level.side,
                        level.price,
                        level.contracts,
                        level.level_rank,
                    )
                    for level in levels
                ],
            )

            conn.execute(
                """
                INSERT INTO liquidity_metrics (
                    ts_utc, ticker,
                    buy_yes_vwap_25, buy_yes_vwap_50, buy_yes_vwap_100,
                    sell_yes_vwap_25, sell_yes_vwap_50, sell_yes_vwap_100,
                    buy_no_vwap_25, sell_no_vwap_25,
                    top_spread_yes, top_spread_no, reason_flags_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts_utc, ticker) DO UPDATE SET
                    buy_yes_vwap_25=excluded.buy_yes_vwap_25,
                    buy_yes_vwap_50=excluded.buy_yes_vwap_50,
                    buy_yes_vwap_100=excluded.buy_yes_vwap_100,
                    sell_yes_vwap_25=excluded.sell_yes_vwap_25,
                    sell_yes_vwap_50=excluded.sell_yes_vwap_50,
                    sell_yes_vwap_100=excluded.sell_yes_vwap_100,
                    buy_no_vwap_25=excluded.buy_no_vwap_25,
                    sell_no_vwap_25=excluded.sell_no_vwap_25,
                    top_spread_yes=excluded.top_spread_yes,
                    top_spread_no=excluded.top_spread_no,
                    reason_flags_json=excluded.reason_flags_json
                """,
                (
                    ts_utc,
                    market.ticker,
                    metrics_row["buy_yes_vwap_25"],
                    metrics_row["buy_yes_vwap_50"],
                    metrics_row["buy_yes_vwap_100"],
                    metrics_row["sell_yes_vwap_25"],
                    metrics_row["sell_yes_vwap_50"],
                    metrics_row["sell_yes_vwap_100"],
                    metrics_row["buy_no_vwap_25"],
                    metrics_row["sell_no_vwap_25"],
                    metrics_row["top_spread_yes"],
                    metrics_row["top_spread_no"],
                    metrics_row.get("reason_flags_json"),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        return connection
