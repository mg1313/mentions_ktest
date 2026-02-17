import sqlite3
from pathlib import Path
from uuid import uuid4

from mentions_sports_poller.mentions_api.reporting_views import apply_reporting_views


def test_reporting_views_sql_applies_and_returns_expected_fields() -> None:
    db_path = Path(f"tasks/test_powerbi_reporting_{uuid4().hex}.sqlite")
    try:
        _create_min_schema_and_seed_data(db_path)

        views = apply_reporting_views(
            db_path=db_path,
            sql_path="powerbi/mentions_reporting_views.sql",
        )
        assert "vw_mentions_snapshot_enriched" in views

        with sqlite3.connect(db_path) as conn:
            view_names = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'view' AND name LIKE 'vw_mentions_%'
                    """
                ).fetchall()
            }
            assert {
                "vw_mentions_market_dim",
                "vw_mentions_levels_long",
                "vw_mentions_top_of_book",
                "vw_mentions_depth_summary",
                "vw_mentions_snapshot_enriched",
            } <= view_names

            snapshot_row = conn.execute(
                """
                SELECT mention_term, seconds_to_close, minutes_to_close, yes_ask_notional_dollars
                FROM vw_mentions_snapshot_enriched
                WHERE ticker = 'KXNBAMENTION-26FEB17BOSLAL-TRAD'
                """
            ).fetchone()
            assert snapshot_row is not None
            mention_term, seconds_to_close, minutes_to_close, yes_ask_notional_dollars = snapshot_row
            assert mention_term == "Trade / Trades / Traded"
            assert abs(seconds_to_close - 3600) <= 1
            assert abs(minutes_to_close - 60.0) <= 0.05
            assert abs(yes_ask_notional_dollars - 16.8) < 1e-6

            depth_row = conn.execute(
                """
                SELECT yes_ask_levels, yes_ask_contracts_total, yes_ask_notional_dollars_total
                FROM vw_mentions_depth_summary
                WHERE ticker = 'KXNBAMENTION-26FEB17BOSLAL-TRAD'
                """
                ).fetchone()
            assert depth_row == (2, 50, 21.1)
    finally:
        if db_path.exists():
            try:
                db_path.unlink()
            except PermissionError:
                pass


def _create_min_schema_and_seed_data(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE market_meta (
                ticker TEXT PRIMARY KEY,
                series_ticker TEXT NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                yes_sub_title TEXT,
                no_sub_title TEXT,
                category TEXT NOT NULL,
                tags TEXT NOT NULL,
                status TEXT NOT NULL,
                close_time_utc TEXT,
                created_time_utc TEXT
            );

            CREATE TABLE orderbook_snapshot (
                ts_utc TEXT NOT NULL,
                ticker TEXT NOT NULL,
                last_trade_price REAL,
                volume INTEGER,
                open_interest INTEGER,
                PRIMARY KEY (ts_utc, ticker)
            );

            CREATE TABLE orderbook_levels (
                ts_utc TEXT NOT NULL,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                contracts INTEGER NOT NULL,
                level_rank INTEGER NOT NULL,
                PRIMARY KEY (ts_utc, ticker, side, level_rank)
            );

            CREATE TABLE liquidity_metrics (
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
            """
        )

        conn.execute(
            """
            INSERT INTO market_meta (
                ticker, series_ticker, title, subtitle, yes_sub_title, no_sub_title,
                category, tags, status, close_time_utc, created_time_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "KXNBAMENTION-26FEB17BOSLAL-TRAD",
                "KXNBAMENTION",
                "What will the announcers say during Boston vs Los Angeles Professional Basketball Game?",
                "",
                "Trade / Trades / Traded",
                "Trade / Trades / Traded",
                "Mentions",
                '["Sports"]',
                "open",
                "2026-02-17T13:00:00Z",
                "2026-02-17T10:00:00Z",
            ),
        )

        conn.execute(
            """
            INSERT INTO orderbook_snapshot (
                ts_utc, ticker, last_trade_price, volume, open_interest
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "2026-02-17T12:00:00Z",
                "KXNBAMENTION-26FEB17BOSLAL-TRAD",
                0.41,
                12,
                34,
            ),
        )

        conn.executemany(
            """
            INSERT INTO orderbook_levels (
                ts_utc, ticker, side, price, contracts, level_rank
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-17T12:00:00Z", "KXNBAMENTION-26FEB17BOSLAL-TRAD", "YES_BID", 0.40, 25, 0),
                ("2026-02-17T12:00:00Z", "KXNBAMENTION-26FEB17BOSLAL-TRAD", "YES_ASK", 0.42, 40, 0),
                ("2026-02-17T12:00:00Z", "KXNBAMENTION-26FEB17BOSLAL-TRAD", "YES_ASK", 0.43, 10, 1),
                ("2026-02-17T12:00:00Z", "KXNBAMENTION-26FEB17BOSLAL-TRAD", "NO_BID", 0.58, 20, 0),
                ("2026-02-17T12:00:00Z", "KXNBAMENTION-26FEB17BOSLAL-TRAD", "NO_ASK", 0.60, 30, 0),
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
            """,
            (
                "2026-02-17T12:00:00Z",
                "KXNBAMENTION-26FEB17BOSLAL-TRAD",
                0.42,
                0.425,
                None,
                0.40,
                None,
                None,
                0.58,
                0.57,
                0.02,
                0.02,
                '{"buy_yes_vwap_100":"INSUFFICIENT_DEPTH"}',
            ),
        )
