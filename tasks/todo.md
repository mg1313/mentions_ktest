# Task: Mentions -> Sports Orderbook Poller + VWAP

## Scope Guard (Hard)
- [x] Confirm project scope is strictly Kalshi `category=Mentions` + `tags=Sports`.
- [x] Confirm non-sports/non-mentions markets are excluded by design and runtime assertions.
- [x] Do not implement any cross-category discovery.

## Pre-flight Checks (Required Before Coding)
- [x] Verify series category/tag values via API.
  - Command result: `/series?category=Mentions&tags=Sports` returned `category=Mentions`, `tags=["Sports"]` for series like `KXNCAABMENTION`, `KXNBAMENTION`, `KXNFLMENTION`.
- [x] Confirm order book payload structure for YES/NO ladders.
  - Command result: `/markets/{ticker}/orderbook` payload includes `orderbook.yes` and `orderbook.no` as `[price_cents, contracts]` ladders.
- [x] Manually inspect at least one orderbook for price-direction correctness.
  - Example ticker: `KXNCAABMENTION-26FEB10VANAUB-TRAN`
  - Observed market quote: `yes_bid=90, yes_ask=95, no_bid=5, no_ask=10`.
  - Orderbook ladders are bid ladders per side; YES asks and NO asks must be derived from complementary bids (`YES_ASK ~= 100 - best NO_BID`, `NO_ASK ~= 100 - best YES_BID`).
- [x] Validate cumulative-liquidity VWAP math with hand-worked example.
  - Example buy-side asks: `(0.80, 20 contracts)`, `(0.85, 10 contracts)`, budget `$20`.
  - Fill: `20` contracts at `$0.80` (cost `$16`) + `4/0.85=4.705882` contracts at `$0.85` (partial level, cost `$4`).
  - Total contracts: `24.705882`, VWAP=`20/24.705882=0.8095238`.

## Implementation Plan
- [x] Build Python package structure and typed config for polling/discovery/scope constraints.
- [x] Implement Kalshi API client with exponential backoff + jitter and request pacing to stay <=20 req/sec.
- [x] Implement Mentions->Sports discovery module (series + open markets) with runtime scope assertions.
- [x] Implement active-set selection: close_time within 72h OR volume/open_interest > 0 OR manually pinned.
- [x] Implement SQLite schema + indexes and idempotent upserts.
- [x] Implement polling engine every 3 minutes; independent 15-minute universe refresh.
- [x] Implement depth truncation rule: per side keep levels until cumulative notional >= $150 OR first N levels (default 20).
- [x] Implement VWAP/liquidity metrics for budgets $25/$50/$100 (plus required $25 buy/sell NO fields and spread fields).
- [x] Persist snapshots, normalized levels, and derived metrics with UTC timestamps.
- [x] Add logging for discovery counts, active-set size, poll cycle duration, and per-market failures.

## Data Flow
- Inputs:
  - Kalshi series endpoint filtered by `category=Mentions` and `tags=Sports`.
  - Kalshi markets endpoint filtered by discovered `series_ticker` and `status=open`.
  - Kalshi orderbook endpoint for active market tickers.
- Transforms:
  - Validate series scope -> collect open markets -> select active set -> fetch orderbooks -> derive YES/NO bid+ask ladders -> truncate depth -> compute spreads + VWAP.
- Outputs:
  - `market_meta`, `orderbook_snapshot`, `orderbook_levels`, `liquidity_metrics` tables in SQLite.

## Error Handling / Retries
- [x] Exponential backoff with jitter for API calls.
- [x] Fail-open per market in poll cycle (log error, continue remaining markets).
- [x] Retry-safe/idempotent writes via primary keys + `ON CONFLICT` upserts.
- [x] Continue poll loop even when universe refresh fails.

## Storage Schema Changes
- [x] Create initial SQLite schema with required tables and indexes:
  - `market_meta`
  - `orderbook_snapshot`
  - `orderbook_levels`
  - `liquidity_metrics`
  - Added `orderbook_snapshot.raw_orderbook_json` for audit/debug replay.
  - Added `liquidity_metrics.reason_flags_json` to record NULL VWAP reason flags.

## Minimal Test Plan (pytest, no network)
- [x] Mock discovery API responses and verify Mentions->Sports-only selection.
- [x] Unit test scope assertion logic for invalid category/tags.
- [x] Unit test VWAP exact fill.
- [x] Unit test VWAP partial final level.
- [x] Unit test VWAP insufficient liquidity -> NULL + reason flag.
- [x] Unit test idempotent writes / dedupe on retries.
- [x] Unit test active-set filtering rules.
- [x] Unit test retry behavior by simulating transient API failures.

## Rollback / Safety Checks
- [x] Changes are additive and isolated to new package/modules.
- [x] DB schema creation is idempotent (`IF NOT EXISTS`).
- [x] Runtime scope assertions prevent out-of-scope persistence.

## Acceptance Criteria
- [ ] Polling loop can run unattended; universe refresh is independent from poll cadence. (Implemented, not 24h soak-tested in this session.)
- [ ] Snapshots persist every 3 minutes for active set. (Cadence implemented; not observed over multi-cycle runtime in this session.)
- [x] VWAP metrics populate correctly for at least one mocked market in tests.
- [x] Non-sports/non-mentions markets are skipped with warning logs.
- [x] Querying by `(ticker, ts_utc)` can recover VWAP for budgeted buy/sell scenarios.

## Progress Notes
- Pre-flight complete before implementation.
- Implemented package skeleton and runtime modules under `src/mentions_sports_poller/`.
- Added strict scope enforcement at series and market levels; invalid markets are skipped and logged.
- Added orderbook normalization (YES/NO bids + derived asks), depth truncation, and budget-based VWAP metrics.
- Added SQLite schema, indexes, idempotent upserts, and raw payload capture for auditability.
- Added poll loop with independent universe refresh cadence and fail-open per-market handling.
- Added pytest suite with mocked client/session behavior and no network dependency.

## Review (to fill at end)
- What changed:
  - Added a full Mentions -> Sports polling pipeline with discovery, active-set filtering, orderbook fetch/normalization, VWAP derivation, and SQLite persistence.
  - Added strict runtime scope assertions to keep only `Mentions` + `Sports`.
  - Added idempotent schema and writes for `market_meta`, `orderbook_snapshot`, `orderbook_levels`, and `liquidity_metrics`.
  - Added tests for scope validation, discovery behavior, active-set logic, orderbook parsing, VWAP edge cases, idempotent writes, and retry behavior.
- Why:
  - To satisfy the requirement for scheduled forward-logged orderbook collection and execution-realistic VWAP for budget-sized trades within the hard Mentions -> Sports scope.
- How tested:
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider`
  - Result: `10 passed`.
- How to run:
  - One cycle: `python -m mentions_sports_poller.main --once`
  - Continuous scheduler: `python -m mentions_sports_poller.main`
  - Example env overrides:
    - `SQLITE_DB_PATH=data/mentions_sports.db`
    - `POLL_INTERVAL_SECONDS=180`
    - `UNIVERSE_REFRESH_SECONDS=900`
    - `PINNED_TICKERS=KXNBAMENTION-26FEB10LALNYK-FOUL`

---

# Task: NBA Link Scout CLI (Schedule -> URL Build -> Link Discovery + Fallback)

## Scope Guard (Hard)
- [x] Keep scope to NBA schedule driven URL visits and user-configured link matching only.
- [x] Do not hardcode target domains/selectors/link rules in code.
- [x] Support multiple target sites via config-driven URL/link rules.

## Plan
- [x] Add a new module tree `src/mentions_sports_poller/nba_link_scout/` with separable components:
  - `models.py` dataclasses for `Game`, `TargetSiteRule`, `LinkSearchRule`, `ExtractionResult`, and config models.
  - `config.py` JSON config loader/validator.
  - `schedule.py` pluggable schedule source interface + `http_json` provider.
  - `game_selection.py` date/team filtering.
  - `url_builder.py` game -> target URL generation from templates.
  - `fetcher.py` isolated HTTP fetcher with retries/backoff/user-agent/timeout.
  - `link_finder.py` HTML parser + URL normalization + include/exclude/constraint filtering.
  - `fallback.py` adapter to load/call an existing extractor module from config path.
  - `runner.py` orchestration flow.
  - `cli.py` command surface (`run`, `dry-run`).
- [x] Add JSON output + optional table output formatting.
- [x] Add CLI entrypoint script `nba-link-scout` in `pyproject.toml`.
- [x] Add `README_nba_link_scout.md` + `configs/nba_link_scout.example.json`.

## Data Flow
- Inputs:
  - `--date` (`YYYY-MM-DD`)
  - JSON config (`schedule_source`, `target_sites`, optional fallback extractor)
- Transforms:
  - Fetch schedule for requested date window -> filter relevant games -> build target URLs -> fetch page -> extract/filter links -> fallback extractor when no HTML matches.
- Outputs:
  - JSON result (default) and optional table print.

## Error Handling / Retries
- [x] Schedule/page fetch with retry + exponential backoff + jitter.
- [x] Structured per-game/per-url errors captured in output debug fields.
- [x] Fail-open behavior per URL/game (continue processing remaining work).

## Minimal Test Plan (pytest, no network)
- [x] Unit test URL builder from game -> URL.
- [x] Unit test HTML extraction + relative URL normalization.
- [x] Unit test include/exclude/constraints filtering.
- [x] Unit test fallback invocation logic with mocked fallback module.
- [x] Add one fixture HTML file and test against it.

## Acceptance Criteria
- [x] `nba-link-scout run --date YYYY-MM-DD --config ...` returns extracted links for matching games.
- [x] `nba-link-scout dry-run --date ... --config ...` performs no network calls and prints planned actions.
- [x] If HTML extraction returns zero links, fallback extractor is invoked and filtered results are returned.
- [x] Tests pass locally.

## Progress Notes
- Identified current stack/conventions: Python package + argparse + dataclasses + pytest.
- Found potential fallback module candidate: `extract_video_url_api.py`.
- Implemented full module layout under `src/mentions_sports_poller/nba_link_scout/` with isolated schedule, fetch, parse, fallback, output, runner, and CLI layers.
- Added config-driven multi-target URL construction and link selection with include/exclude/constraint filtering.
- Added dry-run behavior that avoids all network calls while still rendering schedule request plans and URL extraction plans.
- Added tests + HTML fixture for URL builder, HTML normalization/filtering, and fallback invocation logic.

## Review (to fill at end)
- What changed:
  - Added `nba_link_scout` package modules:
    - `src/mentions_sports_poller/nba_link_scout/models.py`
    - `src/mentions_sports_poller/nba_link_scout/config.py`
    - `src/mentions_sports_poller/nba_link_scout/schedule.py`
    - `src/mentions_sports_poller/nba_link_scout/game_selection.py`
    - `src/mentions_sports_poller/nba_link_scout/url_builder.py`
    - `src/mentions_sports_poller/nba_link_scout/fetcher.py`
    - `src/mentions_sports_poller/nba_link_scout/link_finder.py`
    - `src/mentions_sports_poller/nba_link_scout/fallback.py`
    - `src/mentions_sports_poller/nba_link_scout/output.py`
    - `src/mentions_sports_poller/nba_link_scout/runner.py`
    - `src/mentions_sports_poller/nba_link_scout/cli.py`
    - `src/mentions_sports_poller/nba_link_scout/__main__.py`
  - Added docs/config:
    - `README_nba_link_scout.md`
    - `configs/nba_link_scout.example.json`
  - Added tests/fixtures:
    - `tests/test_nba_link_scout_url_builder.py`
    - `tests/test_nba_link_scout_link_finder.py`
    - `tests/test_nba_link_scout_fallback.py`
    - `tests/fixtures/scout_sample_page.html`
  - Added entrypoints in `pyproject.toml` including `nba-link-scout`.
- Why:
  - Needed a deterministic, config-driven CLI for NBA-date game selection and link discovery with fallback extraction while keeping URL/link rules externalized.
- How tested:
  - `python -m pytest -q` -> 15 passed.
  - `PYTHONPATH=src python -m mentions_sports_poller.nba_link_scout dry-run --date 2026-02-10 --config configs/nba_link_scout.example.json` produced planned JSON output with no fetch calls.
  - Run-mode smoke with local HTTP fixture server + `file_json` schedule config confirmed end-to-end fetch and extraction produced `/watch/` links.
- How to run:
  - `PYTHONPATH=src python -m mentions_sports_poller.nba_link_scout run --date YYYY-MM-DD --config configs/nba_link_scout.example.json`
  - `PYTHONPATH=src python -m mentions_sports_poller.nba_link_scout dry-run --date YYYY-MM-DD --config configs/nba_link_scout.example.json`
  - After install: `nba-link-scout run --date YYYY-MM-DD --config configs/nba_link_scout.example.json`

---

# Task: Basketball-Video -> GuideDesGemmes -> OK.ru Daily File Workflow

## Scope Guard (Hard)
- [x] Keep target matching rules config-driven (no hardcoded one-off selectors).
- [x] Support basketball-video page + intermediary guide links + final OK.ru extraction.
- [x] Keep deterministic output with daily file update behavior.

## Plan
- [x] Extend URL template context for basketball-video date format placeholders.
- [x] Add ordered fallback extractor chain support (`fallback_extractors` list).
- [x] Add optional final `video_link_rule` so output can be constrained to OK.ru URLs.
- [x] Execute fallback extractors on source page and intermediary matched links.
- [x] Add daily output file upsert (`date`, `home`, `away`, `video_url`) and CLI flag/config support.
- [x] Add tests for intermediary fallback flow, output file update, and new URL placeholders.

## Acceptance Criteria
- [x] Basketball-video URL pattern can be rendered with month-name/day format.
- [x] GuideDesGemmes links can be discovered and used as fallback extraction targets.
- [x] API fallback runs before Selenium fallback when configured in order.
- [x] Daily output file updates with deduped rows containing date/home/away/video_url.
- [x] Tests pass locally.

## Progress Notes
- Added `month_name_lower`, `day_unpadded`, and `matchup_slug` URL template placeholders.
- Added `video_link_rule`, `fallback_extractors`, and `daily_video_output_path` config support.
- Runner now executes extractor chain against both source page and intermediary matches.
- Added `--daily-video-output` CLI flag and JSON upsert writer.
- Added target config template: `configs/nba_link_scout.basketball_video.template.json`.
- Added schedule URL support for literal `YYYYMMDD` token and updated NBA scoreboard mapping (`scoreboard.games`, nested team fields).
- Switched basketball-video template to full-season NBA schedule endpoint and added auto-flatten for `leagueSchedule.gameDates[].games[]`.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/nba_link_scout/models.py` for new config/option fields.
  - Updated `src/mentions_sports_poller/nba_link_scout/config.py` for `fallback_extractors`, `video_link_rule`, `daily_video_output_path`.
  - Updated `src/mentions_sports_poller/nba_link_scout/url_builder.py` with basketball-video date placeholders.
  - Updated `src/mentions_sports_poller/nba_link_scout/runner.py` for intermediary-target fallback chaining + daily row generation.
  - Updated `src/mentions_sports_poller/nba_link_scout/output.py` with daily JSON upsert writer.
  - Updated `src/mentions_sports_poller/nba_link_scout/cli.py` for `--daily-video-output`.
  - Fixed `extract_video_url_selenium.py` to import `extract_from_embed_url`.
  - Added `configs/nba_link_scout.basketball_video.template.json`.
  - Added/updated tests:
    - `tests/test_nba_link_scout_fallback.py`
    - `tests/test_nba_link_scout_output.py`
    - `tests/test_nba_link_scout_url_builder.py`
- Why:
  - Needed final output to be daily-updated rows with game identity + resolved video URLs, including chained fallback extraction across intermediary pages.
- How tested:
  - `python -m pytest -q` -> 18 passed.
  - Run-mode smoke with local fixture server confirmed `--daily-video-output` file updates and deduped row writing.
  - Added schedule tests and re-ran suite: `python -m pytest -q` -> 20 passed.
  - Dry-run now resolves NBA URL correctly to `todaysScoreboard_20260210.json`.
  - Re-ran after full-season endpoint update: `python -m pytest -q` -> 21 passed.
  - Dry-run now shows schedule request URL `https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json`.
- How to run:
  - `PYTHONPATH=src python -m mentions_sports_poller.nba_link_scout run --date 2026-02-10 --config configs/nba_link_scout.basketball_video.template.json --daily-video-output data/nba_okru_daily.json`
