// Power Query templates for Mentions SQLite reporting views.
// Usage:
// 1) Create one blank query per section below.
// 2) Replace DatabasePath.
// 3) Paste each block into Advanced Editor.

// Query: MentionsMarketDim
let
    DatabasePath = "C:\\Users\\mgube\\mentions_ktest\\data\\mentions_sports.db",
    ConnectionString = "Driver=SQLite3 ODBC Driver;Database=" & DatabasePath & ";",
    Source = Odbc.Query(ConnectionString, "SELECT * FROM vw_mentions_market_dim")
in
    Source

// Query: MentionsSnapshotEnriched
let
    DatabasePath = "C:\\Users\\mgube\\mentions_ktest\\data\\mentions_sports.db",
    ConnectionString = "Driver=SQLite3 ODBC Driver;Database=" & DatabasePath & ";",
    Source = Odbc.Query(ConnectionString, "SELECT * FROM vw_mentions_snapshot_enriched"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"ts_utc", type text},
            {"close_time_utc", type text},
            {"created_time_utc", type text},
            {"last_trade_price", type number},
            {"volume", Int64.Type},
            {"open_interest", Int64.Type},
            {"buy_yes_vwap_25", type number},
            {"buy_yes_vwap_50", type number},
            {"buy_yes_vwap_100", type number},
            {"sell_yes_vwap_25", type number},
            {"sell_yes_vwap_50", type number},
            {"sell_yes_vwap_100", type number},
            {"buy_no_vwap_25", type number},
            {"sell_no_vwap_25", type number},
            {"top_spread_yes", type number},
            {"top_spread_no", type number},
            {"seconds_to_close", Int64.Type},
            {"minutes_to_close", type number}
        }
    )
in
    Typed

// Query: MentionsTopOfBook
let
    DatabasePath = "C:\\Users\\mgube\\mentions_ktest\\data\\mentions_sports.db",
    ConnectionString = "Driver=SQLite3 ODBC Driver;Database=" & DatabasePath & ";",
    Source = Odbc.Query(ConnectionString, "SELECT * FROM vw_mentions_top_of_book"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"yes_bid_price", type number},
            {"yes_bid_contracts", Int64.Type},
            {"yes_bid_notional_dollars", type number},
            {"yes_ask_price", type number},
            {"yes_ask_contracts", Int64.Type},
            {"yes_ask_notional_dollars", type number},
            {"no_bid_price", type number},
            {"no_bid_contracts", Int64.Type},
            {"no_bid_notional_dollars", type number},
            {"no_ask_price", type number},
            {"no_ask_contracts", Int64.Type},
            {"no_ask_notional_dollars", type number},
            {"top_spread_yes", type number},
            {"top_spread_no", type number}
        }
    )
in
    Typed

// Query: MentionsDepthSummary
let
    DatabasePath = "C:\\Users\\mgube\\mentions_ktest\\data\\mentions_sports.db",
    ConnectionString = "Driver=SQLite3 ODBC Driver;Database=" & DatabasePath & ";",
    Source = Odbc.Query(ConnectionString, "SELECT * FROM vw_mentions_depth_summary"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"levels_captured", Int64.Type},
            {"yes_bid_levels", Int64.Type},
            {"yes_ask_levels", Int64.Type},
            {"no_bid_levels", Int64.Type},
            {"no_ask_levels", Int64.Type},
            {"yes_bid_contracts_total", Int64.Type},
            {"yes_ask_contracts_total", Int64.Type},
            {"no_bid_contracts_total", Int64.Type},
            {"no_ask_contracts_total", Int64.Type},
            {"yes_bid_notional_dollars_total", type number},
            {"yes_ask_notional_dollars_total", type number},
            {"no_bid_notional_dollars_total", type number},
            {"no_ask_notional_dollars_total", type number}
        }
    )
in
    Typed

// Query: MentionsLevelsLong
let
    DatabasePath = "C:\\Users\\mgube\\mentions_ktest\\data\\mentions_sports.db",
    ConnectionString = "Driver=SQLite3 ODBC Driver;Database=" & DatabasePath & ";",
    Source = Odbc.Query(ConnectionString, "SELECT * FROM vw_mentions_levels_long"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"level_rank", Int64.Type},
            {"price", type number},
            {"contracts", Int64.Type},
            {"level_notional_dollars", type number}
        }
    )
in
    Typed
