-- Mentions poller reporting views for Power BI.
-- Source tables: market_meta, orderbook_snapshot, orderbook_levels, liquidity_metrics

DROP VIEW IF EXISTS vw_mentions_market_dim;
CREATE VIEW vw_mentions_market_dim AS
SELECT
    m.ticker,
    m.series_ticker,
    m.title AS market_title,
    m.subtitle AS market_subtitle,
    COALESCE(
        NULLIF(m.yes_sub_title, ''),
        NULLIF(m.no_sub_title, ''),
        NULLIF(m.subtitle, ''),
        m.title
    ) AS mention_term,
    m.yes_sub_title,
    m.no_sub_title,
    m.category,
    m.tags AS tags_json,
    m.status,
    m.created_time_utc,
    m.close_time_utc
FROM market_meta AS m;

DROP VIEW IF EXISTS vw_mentions_levels_long;
CREATE VIEW vw_mentions_levels_long AS
SELECT
    l.ts_utc,
    l.ticker,
    d.market_title,
    d.mention_term,
    l.side,
    l.level_rank,
    l.price,
    l.contracts,
    ROUND(l.price * l.contracts, 6) AS level_notional_dollars
FROM orderbook_levels AS l
LEFT JOIN vw_mentions_market_dim AS d
    ON d.ticker = l.ticker;

DROP VIEW IF EXISTS vw_mentions_top_of_book;
CREATE VIEW vw_mentions_top_of_book AS
WITH best AS (
    SELECT
        l.ts_utc,
        l.ticker,
        MAX(CASE WHEN l.side = 'YES_BID' AND l.level_rank = 0 THEN l.price END) AS yes_bid_price,
        MAX(CASE WHEN l.side = 'YES_BID' AND l.level_rank = 0 THEN l.contracts END) AS yes_bid_contracts,
        MAX(CASE WHEN l.side = 'YES_ASK' AND l.level_rank = 0 THEN l.price END) AS yes_ask_price,
        MAX(CASE WHEN l.side = 'YES_ASK' AND l.level_rank = 0 THEN l.contracts END) AS yes_ask_contracts,
        MAX(CASE WHEN l.side = 'NO_BID' AND l.level_rank = 0 THEN l.price END) AS no_bid_price,
        MAX(CASE WHEN l.side = 'NO_BID' AND l.level_rank = 0 THEN l.contracts END) AS no_bid_contracts,
        MAX(CASE WHEN l.side = 'NO_ASK' AND l.level_rank = 0 THEN l.price END) AS no_ask_price,
        MAX(CASE WHEN l.side = 'NO_ASK' AND l.level_rank = 0 THEN l.contracts END) AS no_ask_contracts
    FROM orderbook_levels AS l
    GROUP BY l.ts_utc, l.ticker
)
SELECT
    b.ts_utc,
    b.ticker,
    d.market_title,
    d.mention_term,
    b.yes_bid_price,
    b.yes_bid_contracts,
    ROUND(b.yes_bid_price * b.yes_bid_contracts, 6) AS yes_bid_notional_dollars,
    b.yes_ask_price,
    b.yes_ask_contracts,
    ROUND(b.yes_ask_price * b.yes_ask_contracts, 6) AS yes_ask_notional_dollars,
    b.no_bid_price,
    b.no_bid_contracts,
    ROUND(b.no_bid_price * b.no_bid_contracts, 6) AS no_bid_notional_dollars,
    b.no_ask_price,
    b.no_ask_contracts,
    ROUND(b.no_ask_price * b.no_ask_contracts, 6) AS no_ask_notional_dollars,
    CASE
        WHEN b.yes_bid_price IS NOT NULL AND b.yes_ask_price IS NOT NULL
            THEN ROUND(b.yes_ask_price - b.yes_bid_price, 6)
        ELSE NULL
    END AS top_spread_yes,
    CASE
        WHEN b.no_bid_price IS NOT NULL AND b.no_ask_price IS NOT NULL
            THEN ROUND(b.no_ask_price - b.no_bid_price, 6)
        ELSE NULL
    END AS top_spread_no
FROM best AS b
LEFT JOIN vw_mentions_market_dim AS d
    ON d.ticker = b.ticker;

DROP VIEW IF EXISTS vw_mentions_depth_summary;
CREATE VIEW vw_mentions_depth_summary AS
SELECT
    l.ts_utc,
    l.ticker,
    d.market_title,
    d.mention_term,
    COUNT(*) AS levels_captured,
    SUM(CASE WHEN l.side = 'YES_BID' THEN 1 ELSE 0 END) AS yes_bid_levels,
    SUM(CASE WHEN l.side = 'YES_ASK' THEN 1 ELSE 0 END) AS yes_ask_levels,
    SUM(CASE WHEN l.side = 'NO_BID' THEN 1 ELSE 0 END) AS no_bid_levels,
    SUM(CASE WHEN l.side = 'NO_ASK' THEN 1 ELSE 0 END) AS no_ask_levels,
    SUM(CASE WHEN l.side = 'YES_BID' THEN l.contracts ELSE 0 END) AS yes_bid_contracts_total,
    SUM(CASE WHEN l.side = 'YES_ASK' THEN l.contracts ELSE 0 END) AS yes_ask_contracts_total,
    SUM(CASE WHEN l.side = 'NO_BID' THEN l.contracts ELSE 0 END) AS no_bid_contracts_total,
    SUM(CASE WHEN l.side = 'NO_ASK' THEN l.contracts ELSE 0 END) AS no_ask_contracts_total,
    ROUND(SUM(CASE WHEN l.side = 'YES_BID' THEN l.price * l.contracts ELSE 0 END), 6) AS yes_bid_notional_dollars_total,
    ROUND(SUM(CASE WHEN l.side = 'YES_ASK' THEN l.price * l.contracts ELSE 0 END), 6) AS yes_ask_notional_dollars_total,
    ROUND(SUM(CASE WHEN l.side = 'NO_BID' THEN l.price * l.contracts ELSE 0 END), 6) AS no_bid_notional_dollars_total,
    ROUND(SUM(CASE WHEN l.side = 'NO_ASK' THEN l.price * l.contracts ELSE 0 END), 6) AS no_ask_notional_dollars_total
FROM orderbook_levels AS l
LEFT JOIN vw_mentions_market_dim AS d
    ON d.ticker = l.ticker
GROUP BY
    l.ts_utc,
    l.ticker,
    d.market_title,
    d.mention_term;

DROP VIEW IF EXISTS vw_mentions_snapshot_enriched;
CREATE VIEW vw_mentions_snapshot_enriched AS
SELECT
    s.ts_utc,
    s.ticker,
    d.market_title,
    d.market_subtitle,
    d.mention_term,
    d.series_ticker,
    d.status AS market_status,
    d.close_time_utc,
    d.created_time_utc,
    CASE
        WHEN d.close_time_utc IS NULL THEN NULL
        ELSE CAST(ROUND((julianday(replace(d.close_time_utc, 'Z', '')) - julianday(replace(s.ts_utc, 'Z', ''))) * 86400.0, 0) AS INTEGER)
    END AS seconds_to_close,
    CASE
        WHEN d.close_time_utc IS NULL THEN NULL
        ELSE ROUND((julianday(replace(d.close_time_utc, 'Z', '')) - julianday(replace(s.ts_utc, 'Z', ''))) * 1440.0, 3)
    END AS minutes_to_close,
    s.last_trade_price,
    s.volume,
    s.open_interest,
    lm.buy_yes_vwap_25,
    lm.buy_yes_vwap_50,
    lm.buy_yes_vwap_100,
    lm.sell_yes_vwap_25,
    lm.sell_yes_vwap_50,
    lm.sell_yes_vwap_100,
    lm.buy_no_vwap_25,
    lm.sell_no_vwap_25,
    lm.top_spread_yes,
    lm.top_spread_no,
    lm.reason_flags_json,
    tob.yes_bid_price,
    tob.yes_bid_contracts,
    tob.yes_bid_notional_dollars,
    tob.yes_ask_price,
    tob.yes_ask_contracts,
    tob.yes_ask_notional_dollars,
    tob.no_bid_price,
    tob.no_bid_contracts,
    tob.no_bid_notional_dollars,
    tob.no_ask_price,
    tob.no_ask_contracts,
    tob.no_ask_notional_dollars
FROM orderbook_snapshot AS s
LEFT JOIN vw_mentions_market_dim AS d
    ON d.ticker = s.ticker
LEFT JOIN liquidity_metrics AS lm
    ON lm.ts_utc = s.ts_utc AND lm.ticker = s.ticker
LEFT JOIN vw_mentions_top_of_book AS tob
    ON tob.ts_utc = s.ts_utc AND tob.ticker = s.ticker;
