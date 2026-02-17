# Power BI Setup for Mentions Poller Data

This folder contains import-ready artifacts for visualizing the Mentions polling data in `data/mentions_sports.db`.

## Files

- `powerbi/mentions_reporting_views.sql`: SQLite views for BI-friendly tables.
- `powerbi/mentions_queries.m`: Power Query templates (ODBC + SQLite).
- `powerbi/mentions_measures.dax`: DAX measures for core market/VWAP/liquidity KPIs.

## 1) Apply Reporting Views (One Time per DB File)

From repo root:

```powershell
python scripts/apply_mentions_reporting_views.py --db-path data/mentions_sports.db
```

This creates/refreshes:

- `vw_mentions_market_dim`
- `vw_mentions_levels_long`
- `vw_mentions_top_of_book`
- `vw_mentions_depth_summary`
- `vw_mentions_snapshot_enriched`

## 2) Connect Power BI to SQLite

Prerequisite: install an SQLite ODBC driver on Windows (for example, `SQLite3 ODBC Driver`).

In Power BI Desktop:

1. Open **Transform Data** -> **Power Query Editor**.
2. Create a blank query for each block in `powerbi/mentions_queries.m`.
3. In each block, update `DatabasePath` to your DB file path.
4. Rename queries to:
   - `vw_mentions_market_dim`
   - `vw_mentions_snapshot_enriched`
   - `vw_mentions_top_of_book`
   - `vw_mentions_depth_summary`
   - `vw_mentions_levels_long`

## 3) Add DAX Measures

1. Open **Model view**.
2. Select the target table (usually `vw_mentions_snapshot_enriched`).
3. Create new measures and paste formulas from `powerbi/mentions_measures.dax`.

## 4) Recommended Relationships

- `vw_mentions_market_dim[ticker]` (1) -> `vw_mentions_snapshot_enriched[ticker]` (many)
- `vw_mentions_market_dim[ticker]` (1) -> `vw_mentions_top_of_book[ticker]` (many)
- `vw_mentions_market_dim[ticker]` (1) -> `vw_mentions_depth_summary[ticker]` (many)
- `vw_mentions_market_dim[ticker]` (1) -> `vw_mentions_levels_long[ticker]` (many)

## 5) Starter Visuals

- Line chart: `ts_utc` vs `buy_yes_vwap_50` by `mention_term`.
- Line chart: `ts_utc` vs `Top YES Ask Dollars Available`.
- Table: `ticker`, `mention_term`, `yes_ask_price`, `yes_ask_notional_dollars`, `minutes_to_close`.
- Scatter: `top_spread_yes` vs `buy_yes_vwap_50` sized by `yes_ask_notional_dollars`.
