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
- Hardened basketball-video fetching against 403 scenarios: no retry on non-retryable HTTP errors, browser-like configurable headers, and fallback extractor execution even when primary fetch fails.
- Added fallback adapter circuit-breaker to disable Selenium extractor after first fatal WebDriver-style failure, reducing repeated stacktraces across games.
- Hardened `extract_video_url_selenium.py` with modern headless options and fail-open behavior (`[]` on WebDriverException) to avoid noisy hard failures.
- Added optional Playwright target-page fetch mode (`http.target_page_fetch_mode`) while keeping schedule fetch on `httpx`.
- Added paired daily output workflow: one row per game with `main_video_url` + `backup_video_url`, preferring links extracted from the same intermediary guide page.
- Updated `RUNBOOK.md` with fully separated workflow sections and added date-range execution script docs.
- Added script `scripts/run_nba_link_range.ps1` to run `nba-link-scout` across an inclusive date range.

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
  - Re-ran after anti-403 hardening: `python -m pytest -q` -> 23 passed.
  - Re-ran after Selenium circuit-breaker: `python -m pytest -q` -> 24 passed.
  - Re-ran after Playwright integration: `python -m pytest -q` -> 26 passed.
  - Re-ran after paired-link workflow update: `python -m pytest -q` -> 27 passed.
  - Script smoke check: `powershell -ExecutionPolicy Bypass -File scripts/run_nba_link_range.ps1 -StartDate 2026-02-09 -EndDate 2026-02-09 -ConfigPath configs/nba_link_scout.basketball_video.template.json -OutputDir data -DryRun` -> success.
- How to run:
  - `PYTHONPATH=src python -m mentions_sports_poller.nba_link_scout run --date 2026-02-10 --config configs/nba_link_scout.basketball_video.template.json --daily-video-output data/nba_okru_daily.json`

---

# Task: Folder Restructure for Mentions API Workflow

## Scope Guard (Hard)
- [x] Do not modify NBA schedule/video workflow logic or locations.
- [x] Move only Mentions data API/poller code into its own workflow section.
- [x] Keep Mentions -> Sports scope behavior unchanged.

## Plan
- [x] Create a dedicated Mentions workflow section under `src/mentions_sports_poller/mentions_api/`.
- [x] Move Mentions modules (`config`, `kalshi_client`, `discovery`, `scope`, `orderbook`, `vwap`, `storage`, `poller`, `time_utils`, `types`, `main`) into that section.
- [x] Update internal imports and package exports to reflect new paths.
- [x] Update CLI entrypoint for Mentions poller to new module path.
- [x] Update Mentions-related tests/imports only.
- [x] Run pytest to verify no behavioral regressions.

## Acceptance Criteria
- [x] Mentions code exists in a dedicated folder section separate from schedule/video workflow code.
- [x] `mentions-sports-poller` entrypoint still runs.
- [x] Existing NBA link scout imports and tests remain unchanged.
- [x] Tests pass after path updates.

## Progress Notes
- Found current mix: Mentions modules at `src/mentions_sports_poller/*` and video workflow at `src/mentions_sports_poller/nba_link_scout/*`.
- Chosen restructure: place Mentions modules under `src/mentions_sports_poller/mentions_api/` and rewire only Mentions imports/entrypoints.
- Moved all Mentions modules into `src/mentions_sports_poller/mentions_api/`.
- Updated package exports in `src/mentions_sports_poller/__init__.py` to import from `mentions_api`.
- Updated script entrypoint in `pyproject.toml` to `mentions_sports_poller.mentions_api.main:main`.
- Updated only Mentions tests to new import paths; NBA tests/imports unchanged.
- Verified with pytest: `27 passed`.

## Review
- What changed:
  - Relocated Mentions workflow modules into `src/mentions_sports_poller/mentions_api/`:
    - `config.py`, `kalshi_client.py`, `discovery.py`, `scope.py`, `orderbook.py`, `vwap.py`, `storage.py`, `poller.py`, `time_utils.py`, `types.py`, `main.py`.
  - Added `src/mentions_sports_poller/mentions_api/__init__.py`.
  - Updated `src/mentions_sports_poller/__init__.py` exports to reference `mentions_api`.
  - Updated `pyproject.toml` entrypoint for `mentions-sports-poller`.
  - Updated Mentions-only tests import paths:
    - `tests/test_vwap.py`
    - `tests/test_storage_idempotent.py`
    - `tests/test_scope_and_discovery.py`
    - `tests/test_retry.py`
    - `tests/test_orderbook.py`
- Why:
  - To separate the Mentions polling/data API workflow from the schedule/video-link workflow while keeping both processes in the same repository.
- How tested:
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `27 passed`.
- How to run:
  - Mentions poller once: `python -m mentions_sports_poller.mentions_api.main --once`
  - Mentions poller continuous: `python -m mentions_sports_poller.mentions_api.main`
  - Installed entrypoint: `mentions-sports-poller --once`

---

# Task: Add Operational Runbook

## Scope Guard
- [x] Add documentation only.
- [x] Do not change workflow logic.

## Plan
- [x] Create standard root runbook file for operational commands.
- [x] Include both workflows with setup, run-once, continuous run, outputs, and troubleshooting.

## Acceptance Criteria
- [x] A single discoverable runbook exists at repo root.
- [x] Commands for running Mentions once are explicit and copy-paste ready.
- [x] Commands for NBA link scout run/dry-run are documented.

## Review
- What changed:
  - Added `RUNBOOK.md` with operational instructions for `mentions-sports-poller` and `nba-link-scout`.
- Why:
  - Provide a single standard operations note for running the functions created in this repo.
- How tested:
  - Verified command paths and module targets against current package layout and entrypoints.
- How to run:
  - Open `RUNBOOK.md` and run commands from repository root.

---

# Task: Audio Download Progress + NBA Game Commentary Info Packets

## Scope Guard
- [x] Keep existing NBA link discovery and audio manifest semantics unchanged.
- [x] Add progress reporting to audio download CLI without introducing non-deterministic dependencies.
- [x] Build game info packets from NBA API endpoints only (no browser scraping).

## Plan
- [x] Add download progress callbacks in audio downloader:
  - Log file index and remaining file count.
  - Emit per-file remaining percentage when byte totals or ETA-based estimates are available.
  - Fallback to ordinal status (`downloading file #n`) when no totals are available.
- [x] Add NBA game info packet builder module:
  - Use existing schedule source config and date filtering.
  - Fetch game boxscore payloads for selected games.
  - Extract home/away rosters and broadcast/commentary metadata.
  - Clearly separate `commentators` (actual names if present) vs `broadcast_teams` (network-level entries).
- [x] Add CLI command surface for info packets:
  - `nba-link-scout game-info --date YYYY-MM-DD --config ... --output ...`
  - Optional `--team` filter and `--dry-run`.
- [x] Add tests (no network):
  - Progress callback behavior for known and unknown totals.
  - Game info extraction from mocked schedule + mocked boxscore payloads.
  - Commentator metadata fallback semantics.
- [x] Update `RUNBOOK.md` with new usage commands.

## Acceptance Criteria
- [x] `nba-audio-dl download ...` logs remaining file count and per-file remaining percentage when available.
- [x] `nba-link-scout game-info --date ...` outputs per-game packets with roster and commentary metadata.
- [x] Tests pass locally with pytest (no network).

## Progress Notes
- Added structured download progress events in `audio_download.py` and wired terminal progress reporting in `audio_cli.py`.
- Progress output now includes per-file ordinal (`file i/N`), remaining files, and estimated remaining percent when available from yt-dlp progress signals.
- Added `game_info.py` packet builder using existing schedule provider + per-game boxscore fetch.
- Added `nba-link-scout game-info` command with `--team`, `--dry-run`, and `--boxscore-url-template`.
- Added tests for progress events and game info packet extraction/fallback commentary behavior.
- Updated `RUNBOOK.md` with the new game-info workflow and audio progress notes.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_download.py`:
    - Added per-file progress callback flow.
    - Added compatibility layer for 2-arg and 3-arg downloader callables.
    - Added yt-dlp hook-based remaining-percent estimation.
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py`:
    - Added live progress reporter output for `download` command.
  - Added `src/mentions_sports_poller/nba_link_scout/game_info.py`:
    - Built per-game packets with roster + commentary metadata.
  - Updated `src/mentions_sports_poller/nba_link_scout/cli.py`:
    - Added `game-info` subcommand.
  - Added tests:
    - `tests/test_nba_link_scout_game_info.py`
    - updated `tests/test_nba_audio_download.py` with progress event assertions.
  - Updated docs:
    - `RUNBOOK.md` (audio progress notes + game-info command usage).
- Why:
  - Needed clearer runtime visibility during long audio downloads and a reusable daily game context packet that includes roster and commentary metadata for downstream transcription.
- How tested:
  - `python -m pytest -q tests/test_nba_audio_download.py tests/test_nba_link_scout_game_info.py -p no:tmpdir -p no:cacheprovider` -> `5 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `32 passed`.
- How to run:
  - Audio download with progress:
    - `python -m mentions_sports_poller.nba_link_scout.audio_cli download --manifest data/nba_audio_manifest.json --output-dir data/audio --date 2026-02-09`
  - Game info packets:
    - `python -m mentions_sports_poller.nba_link_scout game-info --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --output data/nba_game_info_2026-02-09.json`

---

# Task: GPT-4o Audio Transcription with Game Packet + Glossary Context

## Scope Guard
- [x] Transcribe a single downloaded audio file at a time (deterministic one-file workflow).
- [x] Inject both game info packet context and `basketball_glossary.md` into transcription prompt.
- [x] Keep network interactions isolated and mockable for tests.

## Plan
- [x] Add transcription module:
  - Resolve audio row from manifest by `audio_id`.
  - Resolve matching game packet (`date`, `away`, `home`) from game-info JSON.
  - Load glossary file and build prompt context.
  - Call OpenAI audio transcription endpoint with `gpt-4o-transcribe`.
  - Return/write structured output JSON.
- [x] Add CLI command:
  - `nba-audio-dl transcribe --audio-id ... --manifest ... --game-info-file ...`
  - Optional flags: model, glossary path, output path, timeout, dry-run.
- [x] Add tests (no network):
  - Prompt includes game packet + glossary context.
  - Matching packet selection works.
  - API client parsing and output shape works with mocked HTTP response.
- [x] Update `RUNBOOK.md` transcription section with exact commands.

## Acceptance Criteria
- [x] Can transcribe one file via CLI using `gpt-4o-transcribe`.
- [x] Prompt context includes relevant game packet + glossary.
- [x] Tests pass locally with no-network mocking.

## Progress Notes
- Added `transcribe.py` with one-file transcription flow:
  - resolves `audio_id` from manifest
  - resolves matching game packet from game-info file
  - injects packet + glossary text into prompt
  - calls OpenAI `/v1/audio/transcriptions` with model `gpt-4o-transcribe`
  - writes structured JSON output.
- Extended `audio_cli.py` with `transcribe` subcommand and flags for model, glossary path, output path, timeout, and dry-run.
- Added test module `tests/test_nba_transcribe.py` covering packet matching, prompt context composition, and mocked API request/response behavior.
- Updated `RUNBOOK.md` with end-to-end transcription commands.

## Review
- What changed:
  - Added `src/mentions_sports_poller/nba_link_scout/transcribe.py`.
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py` with `transcribe` command.
  - Added `tests/test_nba_transcribe.py`.
  - Updated `RUNBOOK.md` with transcription workflow commands.
- Why:
  - Needed a deterministic one-file transcription workflow that uses both game packet context and basketball glossary context before calling `gpt-4o-transcribe`.
- How tested:
  - `python -m pytest -q tests/test_nba_transcribe.py tests/test_nba_audio_download.py -p no:tmpdir -p no:cacheprovider` -> `6 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `36 passed`.
- How to run:
  - `python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id <AUDIO_ID> --manifest data/nba_audio_manifest.json --game-info-file data/nba_game_info_YYYY-MM-DD.json --glossary-file basketball_glossary.md --output data/transcripts/<AUDIO_ID>.json`

---

# Task: Transcription Test Clip + Progress Percent

## Scope Guard
- [x] Keep existing one-file transcription behavior default unchanged.
- [x] Add optional first-N-seconds transcription mode for quick tests.
- [x] Add deterministic, visible percent progress for transcription CLI.

## Plan
- [x] Add `--max-seconds` support in transcription workflow:
  - Clip source audio to first N seconds before API upload.
  - Use ffmpeg for clipping and keep implementation isolated/testable.
- [x] Add transcription progress callback/events:
  - Stage-based percent updates from start to completion.
  - CLI output should show `%` progress.
- [x] Add tests (no network):
  - Progress callback emits expected stage percents.
  - Max-seconds path invokes clipper and transcribes clipped path.
- [x] Update `RUNBOOK.md` with quick 30-second test command.

## Acceptance Criteria
- [x] User can run `transcribe --max-seconds 30` to test on first 30 seconds.
- [x] CLI prints percent progress during transcription.
- [x] Tests pass locally.

## Progress Notes
- Added `max_seconds` clipping support in `transcribe.py` with ffmpeg-backed clip creation before upload.
- Added transcription progress events (`transcription_progress`) and stage percentages in the core transcription flow.
- Added `TranscriptionProgressReporter` in `audio_cli.py` to print progress percent lines during transcribe runs.
- Added CLI flags `--max-seconds` and `--ffmpeg-bin` to `nba-audio-dl transcribe`.
- Updated `RUNBOOK.md` with first-30-seconds quick test command and progress notes.
- Added test coverage for max-seconds clipping path and progress percentage event emission.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/nba_link_scout/transcribe.py`:
    - Added optional clipping (`max_seconds`) via ffmpeg.
    - Added progress callback events with stage-based percents.
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py`:
    - Added `--max-seconds`, `--ffmpeg-bin`.
    - Added `TranscriptionProgressReporter`.
  - Updated docs: `RUNBOOK.md`.
  - Updated tests: `tests/test_nba_transcribe.py`.
- Why:
  - Needed fast test transcriptions on only first 30s and visible progress feedback for long-running transcribe calls.
- How tested:
  - `python -m pytest -q tests/test_nba_transcribe.py -p no:tmpdir -p no:cacheprovider`
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider`
- How to run:
  - `python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id <AUDIO_ID> --manifest data/nba_audio_manifest.json --game-info-file data/nba_game_info_YYYY-MM-DD.json --glossary-file basketball_glossary.md --max-seconds 30 --output data/transcripts/<AUDIO_ID>.test30s.json`

---

# Task: Deterministic Name/Nickname Correction + Chunked Transcription

## Scope Guard
- [x] Apply deterministic correction only to player names, commentator names, and team nicknames.
- [x] Do not include city names in correction entities.
- [x] Add chunking suitable for long files with pragmatic 80/20 implementation.

## Plan
- [x] Build correction entity set from game packet + audio metadata:
  - players from rosters
  - commentators from commentary packet
  - team nicknames only (no city names)
- [x] Add deterministic correction pass:
  - fuzzy + canonical casing normalization
  - replacement audit list in output JSON
- [x] Add chunking pipeline:
  - duration probe with ffprobe
  - fixed-size chunk plan with optional overlap
  - sequential chunk transcription and merge
- [x] Wire chunk options into CLI.
- [x] Add tests for correction scope and chunking behavior.

## Acceptance Criteria
- [x] Misspelled player/commentator/team nickname tokens can be corrected deterministically.
- [x] City names are not part of correction entity catalog.
- [x] Long audio can be transcribed in chunks with configurable chunk size/overlap.
- [x] Tests pass.

## Progress Notes
- Reworked transcription engine to support chunk planning (`chunk_seconds`, `chunk_overlap_seconds`) and per-chunk uploads.
- Added deterministic entity correction targeting:
  - player full names
  - commentator names
  - NBA team nicknames (city excluded by design)
- Added output fields: `transcript_text_raw`, `transcript_text`, `entity_corrections`, `correction_entities`, and `chunks`.
- Added CLI flags:
  - `--chunk-seconds`
  - `--chunk-overlap-seconds`
  - `--ffprobe-bin`
- Extended tests for:
  - deterministic corrections without city correction
  - chunked multi-request transcription path
  - progress event expectations.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/nba_link_scout/transcribe.py`.
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py`.
  - Updated `tests/test_nba_transcribe.py`.
  - Updated `RUNBOOK.md`.
- Why:
  - Needed robust handling for long (2-hour) audio and deterministic cleanup of common proper-noun misses.
- How tested:
  - `python -m pytest -q tests/test_nba_transcribe.py -p no:tmpdir -p no:cacheprovider` -> `6 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `38 passed`.
- How to run:
  - Chunked run:
    - `python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id <AUDIO_ID> --manifest data/nba_audio_manifest.json --game-info-file data/nba_game_info_YYYY-MM-DD.json --glossary-file basketball_glossary.md --chunk-seconds 900 --chunk-overlap-seconds 0 --output data/transcripts/<AUDIO_ID>.json`

---

# Task: Transcribe CLI Defaults (Auto Game Info + Optional Output)

## Scope Guard
- [x] Keep existing explicit flags supported for backwards compatibility.
- [x] Make `--game-info-file` optional by deriving date from audio manifest row.
- [x] Keep chunk defaults at 900/0 and keep those flags optional in CLI calls.

## Plan
- [x] Add manifest-driven game-info path resolution for transcribe command.
- [x] Add default output naming rules:
  - `<audio_id>.json` under `data/transcripts` when full file.
  - `<audio_id>.test#s.json` when `--max-seconds` is set and `--output` omitted.
- [x] Add tests for auto path resolution + output default behavior.
- [x] Update `RUNBOOK.md` command examples to omit manual game-info/output where appropriate.

## Acceptance Criteria
- [x] User can run transcribe without manually passing `--game-info-file` if standard file naming exists.
- [x] User can omit `--output` and get deterministic default file naming.
- [x] Tests pass.

## Progress Notes
- Made `--game-info-file` optional in `audio_cli.py` and added manifest-driven resolution:
  - finds audio row by `audio_id`
  - reads `date`
  - auto-resolves to `<game-info-dir>/nba_game_info_<date>.json` (default `data/`)
- Added optional `--game-info-dir` to support custom auto-resolution directory while preserving default behavior.
- Added default transcript output naming in `transcribe.py`:
  - normal: `data/transcripts/<audio_id>.json`
  - test clip: `data/transcripts/<audio_id>.test#s.json`
- Updated runbook examples to show shorter CLI calls without manual game-info/output flags for the common path.
- Added tests:
  - `tests/test_nba_audio_cli_transcribe_defaults.py`
  - extended `tests/test_nba_transcribe.py` for default output suffix with `--max-seconds`.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py` for auto game-info resolution and parser changes.
  - Updated `src/mentions_sports_poller/nba_link_scout/transcribe.py` for default output naming with `.test#s` suffix when `max_seconds` is set.
  - Added `tests/test_nba_audio_cli_transcribe_defaults.py`.
  - Updated `tests/test_nba_transcribe.py`.
  - Updated `RUNBOOK.md`.
- Why:
  - Remove manual lookup friction in the transcribe CLI and make defaults match daily usage patterns.
- How tested:
  - `python -m pytest -q tests/test_nba_audio_cli_transcribe_defaults.py tests/test_nba_transcribe.py -p no:tmpdir -p no:cacheprovider` -> `9 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `41 passed`.
- How to run:
  - `python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id <AUDIO_ID> --manifest data/nba_audio_manifest.json --glossary-file basketball_glossary.md`

---

# Task: Transcript Feature Dataset Builder (Utterance Modeling Prep)

## Scope Guard
- [x] Process final corrected transcript outputs into modeling-ready rows.
- [x] Keep all processing deterministic and local (no network).
- [x] Include factors needed for downstream modeling:
  - per-term utterance counts
  - national-vs-local indicator
  - commentator presence
  - player presence

## Plan
- [x] Add `transcript_dataset.py` module:
  - load transcript JSON files and manifest rows
  - load per-date game info packets
  - count configured terms in corrected transcript text
  - derive metadata/features for modeling
- [x] Add CLI command to `audio_cli.py`:
  - `nba-audio-dl build-dataset --terms-file ...`
  - allow transcript/manifest/game-info dirs and output path overrides
- [x] Output both:
  - machine-readable JSON payload (`audio_rows` + `game_rows`)
  - flat CSV (`audio_rows`) for direct model ingestion
- [x] Add tests (no network):
  - term counting behavior
  - metadata join from transcript -> manifest -> game packet
  - commentator/player/national feature columns
- [x] Update `RUNBOOK.md` with commands and expected outputs.

## Data Flow
- Inputs:
  - `data/transcripts/*.json` (or override dir)
  - `data/nba_audio_manifest.json` (or override path)
  - `data/nba_game_info_YYYY-MM-DD.json` packets (or override dir)
  - user term definitions (`--terms-file`)
- Transforms:
  - transcript load -> corrected text selection -> term counting -> context joins -> feature vector expansion
- Outputs:
  - JSON dataset artifact (full rich structure)
  - CSV dataset artifact (flat per-audio rows)

## Error Handling / Safety
- [x] Fail-open per transcript file:
  - log and collect row-level errors, continue remaining files.
- [x] Fail-fast for invalid term config schema.
- [x] Missing manifest/game-info context should not crash the full run:
  - preserve row with warnings and empty/default features.

## Storage Schema Changes
- [x] No database schema changes (file outputs only).

## Minimal Test Plan
- [x] Unit test literal phrase counting and case-insensitive matching.
- [x] Unit test dataset row contains expected term count columns.
- [x] Unit test commentator/player presence columns and national flag derivation.
- [x] Unit test game-level aggregation output.

## Acceptance Criteria
- [x] One command builds modeling-ready rows from existing transcript outputs.
- [x] Output contains per-term counts and covariates for feed/commentator/player context.
- [x] Tests pass locally with no-network execution.

## Progress Notes
- Added `src/mentions_sports_poller/nba_link_scout/transcript_dataset.py` with:
  - terms loader (`--terms-file` JSON/text + repeatable `--term`)
  - corrected transcript text selection logic
  - per-term counting (literal or regex rules)
  - manifest + game-info context joins
  - TV scope features (`is_national_tv`, `is_local_tv`, `tv_scope_label`), commentator/player feature expansion
  - per-audio rows + per-game aggregated rows
  - JSON + CSV writers
- Added new CLI command:
  - `python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset ...`
  - supports transcript/manifest/game-info path overrides and output overrides.
- Added tests:
  - `tests/test_nba_transcript_dataset.py`
  - covers feature extraction, aggregation, CSV/JSON output, and fail-open on malformed transcript file.
- Updated `RUNBOOK.md` with section `4.8 Build Modeling Dataset from Final Transcripts`.
- Added starter terms config: `configs/transcript_terms.example.json`.

## Review
- What changed:
  - Added `src/mentions_sports_poller/nba_link_scout/transcript_dataset.py`.
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py` with `build-dataset` subcommand.
  - Added `tests/test_nba_transcript_dataset.py`.
  - Added `configs/transcript_terms.example.json`.
  - Updated `RUNBOOK.md`.
- Why:
  - Needed deterministic preprocessing from corrected transcripts into modeling-ready features for term-count outcome modeling and covariates (broadcast/commentator/player context).
- How tested:
  - `python -m pytest -q tests/test_nba_transcript_dataset.py -p no:tmpdir -p no:cacheprovider` -> `2 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `43 passed`.
  - CLI help smoke:
    - `$env:PYTHONPATH='src'; python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --help`
  - CLI build smoke:
    - `$env:PYTHONPATH='src'; python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --terms-file configs/transcript_terms.example.json --output-json tests/fixtures/_dataset_smoke.json --skip-csv`
- How to run:
  - `python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --transcripts-dir data/transcripts --manifest data/nba_audio_manifest.json --game-info-dir data --terms-file configs/transcript_terms.example.json`

---

# Task: Incremental Game/Term Dataset Modes (Append-Only)

## Scope Guard
- [x] Add append-only dataset updates (no delete/reinsert cycle).
- [x] Support build mode for game factors and build mode for terms.
- [x] Keep term mode limited to previously processed games from game dataset.
- [x] Represent multiple transcripts for the same game as separate feed-level rows.

## Plan
- [x] Extend `build-dataset` CLI with mode selection (`game`, `term`, `both`).
- [x] Add persistent game factors dataset keyed by `game_id`.
- [x] Add persistent term mentions dataset keyed by (`game_id`, `term`).
- [x] Add persistent term registry so game runs can re-apply previously-run terms.
- [x] Ensure:
  - game mode updates game table and backfills term rows for registered terms.
  - term mode updates term rows across all games already in game table.
- [x] Add tests for append-only behavior and mode interactions.
- [x] Update runbook usage examples.

## Data Flow
- Inputs:
  - `data/nba_game_info_YYYY-MM-DD.json`
  - `data/transcripts/*.json`
  - `data/nba_audio_manifest.json`
  - term arguments (`--term`/`--terms-file`)
- Transforms:
  - game packet extraction -> append new `game_id` rows
  - transcript aggregation by `game_id` -> term counting -> append missing (`game_id`,`term`) rows
- Outputs:
  - append-only game factors CSV
  - append-only term mentions CSV
  - term registry JSON

## Acceptance Criteria
- [x] `build-dataset --mode game` appends new game rows and applies previously-registered terms to missing game/term rows.
- [x] `build-dataset --mode term --term "x"` appends missing rows for that term across all known games.
- [x] Existing rows are not deleted/reinserted.
- [x] Tests pass.

## Progress Notes
- Added incremental dataset engine in `transcript_dataset.py`:
  - `build_incremental_game_term_datasets(...)`
  - append-only game factors CSV + term mentions CSV + term registry JSON.
  - game/term rows are feed-level (`audio_id`/`feed_label`) so same `game_id` can have multiple rows.
- Added new default output helpers:
  - `default_game_factors_path()`
  - `default_game_term_mentions_path()`
  - `default_term_registry_path()`
- Updated `audio_cli.py` `build-dataset` behavior:
  - new `--mode {auto,game,term,both,snapshot}`
  - auto mode resolves to:
    - `game` when no term args provided
    - `term` when term args provided
  - incremental modes avoid rewrite and append only missing keys.
- Added tests:
  - `tests/test_nba_transcript_dataset_incremental.py` (game->term->game backfill workflow)
  - `tests/test_nba_transcript_dataset_incremental.py` (multi-feed same-game separation)
  - `tests/test_nba_audio_cli_dataset_mode.py` (mode resolution).
- Updated `RUNBOOK.md` section `4.8` with mode-specific commands and semantics.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/nba_link_scout/transcript_dataset.py` with append-only incremental dataset functions.
  - Updated `src/mentions_sports_poller/nba_link_scout/audio_cli.py` to support incremental/snapshot dataset modes.
  - Added `tests/test_nba_transcript_dataset_incremental.py`.
  - Added `tests/test_nba_audio_cli_dataset_mode.py`.
  - Updated `RUNBOOK.md`.
- Why:
  - Needed two persistent datasets:
    1) game factors keyed by `game_id`,
    2) game-term mentions keyed by (`game_id`,`term`),
    with append-only updates and term registry-driven backfill behavior.
- How tested:
  - `python -m pytest -q tests/test_nba_transcript_dataset_incremental.py tests/test_nba_audio_cli_dataset_mode.py -p no:tmpdir -p no:cacheprovider` -> `4 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `47 passed`.
  - CLI help check:
    - `$env:PYTHONPATH='src'; python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --help`
- How to run:
  - Game factors + backfill prior terms:
    - `python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --mode game --game-info-dir data --transcripts-dir data/transcripts --manifest data/nba_audio_manifest.json`
  - New term across existing games:
    - `python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --mode term --term "buzzer" --game-info-dir data --transcripts-dir data/transcripts --manifest data/nba_audio_manifest.json`

---

# Task: Remove Raw Orderbook Payload Storage (Mentions)

## Scope Guard
- [x] Mentions API workflow only.
- [x] No changes to NBA link scout workflow.

## Plan
- [x] Remove `raw_orderbook_json` from `orderbook_snapshot` schema definition for new DBs.
- [x] Remove raw payload write path from `persist_market_poll` and poller callsite.
- [x] Update tests to reflect lean snapshot schema.
- [x] Run pytest verification.

## Storage Schema Changes
- [x] `orderbook_snapshot` no longer includes `raw_orderbook_json` in code-defined schema.
- [x] Snapshot writes now include only: `ts_utc`, `ticker`, `last_trade_price`, `volume`, `open_interest`.
- [x] Existing DB files with historical `raw_orderbook_json` columns are backward-compatible; new writes do not populate that column.

## Acceptance Criteria
- [x] Poller no longer persists raw orderbook JSON.
- [x] Core price/depth data remains captured via `orderbook_levels`.
- [x] Tests pass.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/mentions_api/storage.py` to remove raw JSON column from schema and insert/update SQL.
  - Updated `src/mentions_sports_poller/mentions_api/poller.py` to stop passing serialized raw payloads.
  - Updated `tests/test_storage_idempotent.py` to match new function signature and assert `raw_orderbook_json` is absent in schema.
- Why:
  - Reduce storage growth and keep collection focused on required price/size/time fields.
- How tested:
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `47 passed`.
- How to run:
  - One-shot: `python -m mentions_sports_poller.mentions_api.main --once`
  - Continuous: `python -m mentions_sports_poller.mentions_api.main`

---

# Task: Persist Human-Readable Mention Phrasing

## Scope Guard
- [x] Mentions API workflow only.
- [x] Use existing tables where possible (no unnecessary new table).

## Plan
- [x] Extend `market_meta` schema to store human-readable phrasing fields from Kalshi market metadata.
- [x] Update discovery parsing to capture phrasing (`subtitle`, `yes_sub_title`, `no_sub_title`).
- [x] Update `upsert_market_meta` writes and add backward-safe migration for existing DB files.
- [x] Update/add tests for discovery parsing and schema migration behavior.
- [x] Run pytest verification.

## Acceptance Criteria
- [x] Human-readable market phrasing is persisted in SQLite.
- [x] Existing DBs are handled without manual destructive reset.
- [x] Tests pass.

## Review
- What changed:
  - Added human-readable phrasing fields to Mentions market model and persistence path:
    - `subtitle`
    - `yes_sub_title`
    - `no_sub_title`
  - Updated discovery parsing in `src/mentions_sports_poller/mentions_api/discovery.py` to capture these fields from Kalshi market payloads.
  - Updated schema/upsert in `src/mentions_sports_poller/mentions_api/storage.py`:
    - `market_meta` now includes new phrasing columns.
    - Added non-destructive migration logic (`ALTER TABLE ... ADD COLUMN`) for existing DBs missing these columns.
  - Updated tests:
    - `tests/test_scope_and_discovery.py` validates phrasing extraction.
    - `tests/test_storage_idempotent.py` validates phrasing columns exist and migration works.
  - Updated runbook table description in `RUNBOOK.md`.
- Why:
  - Persist human-readable mention phrasing in an existing metadata table to support easier market interpretation/querying without adding new tables.
- How tested:
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `49 passed`.
- How to run:
  - Poll once to populate/update phrasing fields:
    - `python -m mentions_sports_poller.mentions_api.main --once`
  - Query phrasing from SQLite:
    - `SELECT ticker, title, subtitle, yes_sub_title, no_sub_title FROM market_meta LIMIT 20;`

---

# Task: Connect Kalshi Mentions Terms to Transcript Dataset Updates

## Scope Guard
- [x] Kept Mentions -> Sports market scope unchanged.
- [x] Implemented only a simple bridge between existing Mentions polling and existing transcript dataset builder.
- [x] No changes to non-sports ingestion.

## Plan
- [x] Reuse existing incremental transcript dataset API (`mode=term`) instead of adding a new dataset pipeline.
- [x] Extract Kalshi term list from current Mentions markets each poll cycle.
- [x] Diff against term registry and run dataset update for newly-seen terms only.
- [x] Keep sync fail-open so term sync failure cannot crash Mentions polling.
- [x] Add unit tests for extraction and new-term-only sync behavior.
- [x] Run full pytest suite.

## Data Flow
- Inputs:
  - Mentions active universe in-memory market list
  - Transcript registry JSON (`data/modeling/nba_terms_registry.json` by default)
- Transforms:
  - Extract term candidate names from ticker suffix + human phrase hints
  - Compare with registry names
  - If unseen terms exist, call incremental transcript dataset builder in `term` mode for only those terms
- Outputs:
  - Updated term registry JSON
  - Appended rows in game term mentions CSV for new terms

## Error Handling / Safety
- [x] Integration is wrapped in `try/except` in poller; failures are logged and poll cycle continues.
- [x] If term registry is missing/invalid, sync treats it as empty and proceeds safely.

## Acceptance Criteria
- [x] Every poll cycle can check for newly discovered Kalshi terms.
- [x] New terms trigger incremental transcript dataset updates.
- [x] No new terms -> no dataset rebuild work.
- [x] Tests pass.

## Review
- What changed:
  - Added `src/mentions_sports_poller/mentions_api/term_sync.py` with:
    - Kalshi term extraction
    - registry diffing
    - incremental term dataset sync hook
  - Updated `src/mentions_sports_poller/mentions_api/poller.py` to call term sync each cycle.
  - Extended `src/mentions_sports_poller/mentions_api/config.py` with transcript sync env settings.
  - Added tests in `tests/test_mentions_term_sync.py`.
  - Updated `RUNBOOK.md` with automatic term sync behavior/config.
- Why:
  - Connect the two workflows so Kalshi mentions terms automatically propagate into transcription dataset term coverage, without manual term entry.
- How tested:
  - `python -m pytest -q tests/test_mentions_term_sync.py -p no:tmpdir -p no:cacheprovider` -> `2 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `51 passed`.
- How to run:
  - Existing Mentions poller commands unchanged; term sync runs automatically unless `SYNC_TRANSCRIPT_TERMS_ENABLED=false`.

---

# Task: Fix Truncated Kalshi Term Names in Transcript Sync

## Scope Guard
- [x] Mentions->transcript term sync path only.
- [x] No changes to polling scope or non-sports logic.

## Plan
- [x] Diagnose why term names in `nba_game_term_mentions.csv` appear as 4-char abbreviations.
- [x] Update extraction to prefer human-readable phrase fields over ticker suffix codes.
- [x] Parse structured `custom_strike` objects correctly (no dict stringification).
- [x] Keep fallback to ticker suffix only when no phrase exists.
- [x] Update tests and run full pytest suite.

## Root Cause
- Term `name` was derived from ticker suffix (e.g., `AIRB`, `CROW`) which is often a 4-character contract code.
- `custom_strike` from Kalshi can be structured (dict). Previous normalization converted dict to string, yielding malformed patterns like `{"Word": ...}`.

## Acceptance Criteria
- [x] New term definitions use full human-readable phrasing where available.
- [x] Structured custom strike values are parsed into usable term patterns.
- [x] Tests pass.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/mentions_api/term_sync.py`:
    - parse `custom_strike` dict/list/string values
    - split multi-variant phrases (e.g. `A / B / C`)
    - derive canonical full term names from phrase text
    - build regex patterns for multi-variant terms
    - fallback to ticker suffix only when no human phrase exists
  - Updated `tests/test_mentions_term_sync.py` expectations for full term names.
- Why:
  - Ensure dataset terms reflect human-readable Kalshi mentions, not abbreviated ticker codes.
- How tested:
  - `python -m pytest -q tests/test_mentions_term_sync.py -p no:tmpdir -p no:cacheprovider` -> `2 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `51 passed`.
- How to run:
  - Run Mentions poller (`--once` or continuous); sync will add full-term entries for newly discovered terms automatically.
  - Existing historical 4-char rows are append-only history and remain unless you reset/regenerate term outputs.

---

# Task: Audit 3-Minute Pipeline Outputs (Mentions + Transcript Sync)

## Scope Guard
- [x] Reviewed Mentions polling and transcription term update outputs only.
- [x] Applied targeted fixes only where behavior diverged from expected term semantics.

## Review Findings
- [x] Mentions polling is current and writing every cycle.
  - `orderbook_snapshot` max timestamp lag observed around ~0.3-0.5 minutes.
  - `orderbook_snapshot`, `orderbook_levels`, and `liquidity_metrics` row counts are growing.
- [x] Transcript term sync had legacy truncated aliases from earlier runs (`airb`, `crow`, etc.).

## Fixes Applied
- [x] Added alias-inference migration from registry legacy pattern literals (`{"Word": ...}` style strings).
- [x] Added automatic migration for both:
  - `data/modeling/nba_terms_registry.json`
  - `data/modeling/nba_game_term_mentions.csv`
- [x] Added tests covering:
  - direct alias migration
  - inferred alias migration when markets do not include the old suffix term.

## Validation
- [x] `python -m pytest -q tests/test_mentions_term_sync.py -p no:tmpdir -p no:cacheprovider` -> `4 passed`.
- [x] `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `53 passed`.
- [x] One-time local migration run applied:
  - inferred aliases: 10
  - registry rows migrated: 10
  - term CSV rows migrated: 180

## Post-Fix Data Check
- [x] Registry short aliases reduced to only legitimate short terms (`mvp`, `nhl`, etc.) and numeric phrases.
- [x] Term CSV short aliases similarly reduced; no remaining legacy ticker-code artifacts among migrated set.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/mentions_api/term_sync.py` to infer/migrate legacy aliases using registry pattern literals and apply deduped CSV rewrites.
  - Updated `tests/test_mentions_term_sync.py` with regression coverage.
- Why:
  - Ensure 3-minute sync data reflects human-readable Kalshi terms and cleans historical short-code artifacts.
- How tested:
  - Full pytest pass and direct artifact inspection after migration.
- How to run:
  - Existing 3-minute poller run commands unchanged; migration logic executes inside sync path.

---

# Task: Restrict Mentions Poller to Professional Basketball Game Markets

## Scope Guard
- [x] Mentions API workflow only.
- [x] Keep existing `Mentions` + `Sports` scope assertions intact.
- [x] Add additional market-type narrowing to only markets whose title indicates `Professional Basketball Game`.

## Plan
- [x] Add a configurable required title phrase in Mentions settings (default `Professional Basketball Game`) to avoid hard-coded literals in logic.
- [x] Apply market filtering during discovery after existing scope assertion, skipping non-matching markets with warning logs.
- [x] Update discovery tests to verify only Professional Basketball Game markets are returned.
- [x] Run pytest for discovery and full suite.

## Acceptance Criteria
- [x] Universe refresh includes only open Mentions->Sports markets with `Professional Basketball Game` in title.
- [x] Other Mentions->Sports market types are skipped and logged.
- [x] Tests pass.

## Review
- What changed:
  - Updated `src/mentions_sports_poller/mentions_api/discovery.py` to apply a title-substring gate after scope assertion, defaulting to `Professional Basketball Game`.
  - Updated `src/mentions_sports_poller/mentions_api/config.py` with new env setting `REQUIRED_MARKET_TITLE_SUBSTRING`.
  - Updated `src/mentions_sports_poller/mentions_api/poller.py` to pass that setting into discovery.
  - Updated `tests/test_scope_and_discovery.py` to cover:
    - only professional basketball markets included by default
    - optional override that disables the title filter.
- Why:
  - Narrow the active universe to only the market type you care about now, while keeping Mentions->Sports constraints intact.
- How tested:
  - `python -m pytest -q tests/test_scope_and_discovery.py -p no:tmpdir -p no:cacheprovider` -> `4 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `54 passed`.
- How to run:
  - Default (basketball-only): `python -m mentions_sports_poller.mentions_api.main --once`
  - Override phrase if needed: `REQUIRED_MARKET_TITLE_SUBSTRING=\"Professional Basketball Game\" python -m mentions_sports_poller.mentions_api.main --once`

---

# Task: Power BI Starter Pack for Mentions Poller Data

## Scope Guard
- [x] Mentions polling SQLite data only (`market_meta`, `orderbook_snapshot`, `orderbook_levels`, `liquidity_metrics`).
- [x] No changes to polling logic or data collection behavior.
- [x] Deliver import-ready artifacts for Power BI (`.sql`, `.m`, `.dax`, usage guide).

## Plan
- [x] Add SQL reporting views file to shape market metadata, snapshot metrics, top-of-book, and depth summaries for BI.
- [x] Add Power Query template file that loads those views from SQLite through ODBC.
- [x] Add DAX measures file for core KPIs (VWAP, spreads, liquidity coverage, time-to-close, market counts).
- [x] Add runbook-style instructions specific to Power BI import and refresh.
- [x] Add pytest coverage that validates the reporting SQL script can be applied and queried locally (no network).

## Acceptance Criteria
- [x] User can point Power BI to SQLite DB and import prebuilt reporting views.
- [x] User has ready-to-paste DAX measures.
- [x] Artifacts are documented with minimal setup steps.
- [x] Tests pass.

## Review
- What changed:
  - Added BI view pack in `powerbi/mentions_reporting_views.sql`:
    - `vw_mentions_market_dim`
    - `vw_mentions_levels_long`
    - `vw_mentions_top_of_book`
    - `vw_mentions_depth_summary`
    - `vw_mentions_snapshot_enriched`
  - Added Power Query templates in `powerbi/mentions_queries.m`.
  - Added DAX KPI pack in `powerbi/mentions_measures.dax`.
  - Added setup guide in `powerbi/README.md`.
  - Added helper script `scripts/apply_mentions_reporting_views.py`.
  - Added reusable helper `src/mentions_sports_poller/mentions_api/reporting_views.py`.
  - Added SQL validation test `tests/test_powerbi_reporting_views.py`.
  - Added runbook pointer in `RUNBOOK.md` section `3.6`.
- Why:
  - Provide an easy Power BI starter workflow without requiring a prebuilt `.pbix` binary.
- How tested:
  - `python -m pytest -q tests/test_powerbi_reporting_views.py -p no:tmpdir -p no:cacheprovider` -> `1 passed`.
  - `python -m pytest -q -p no:tmpdir -p no:cacheprovider` -> `55 passed`.
- How to run:
  - Apply views: `python scripts/apply_mentions_reporting_views.py --db-path data/mentions_sports.db`
  - Follow `powerbi/README.md` to import M queries and DAX measures.

---

# Task: Add Persistent Repository Workflow Summaries

## Scope Guard
- [x] Documentation-only change; no runtime logic changes.
- [x] Keep summaries aligned with current repo behavior across Mentions + NBA pipelines.
- [x] Add references so future tasks review and maintain these docs.

## Plan
- [x] Create 3 markdown files for:
  - LLM-oriented technical context
  - Detailed technical human-readable architecture/workflow reference
  - Intuition-building narrative essay
- [x] Add references in operational and agent-instruction markdown files.
- [x] Add explicit agent rule to review LLM summary first and keep all three docs in sync with code changes.

## Acceptance Criteria
- [x] Three new `.md` files exist and are discoverable.
- [x] Existing `.md` files reference these docs.
- [x] Agent rules explicitly require checking the LLM summary for fast project context.

## Review
- What changed:
  - Added:
    - `docs/repo_context_llm.md`
    - `docs/repo_technical_reference.md`
    - `docs/repo_intuition_essay.md`
  - Updated:
    - `agents.md`
    - `RUNBOOK.md`
    - `README_nba_link_scout.md`
- Why:
  - To keep a durable, updatable context pack for future LLM/human tasks and reduce onboarding overhead.
- How tested:
  - Manual verification that each referenced path exists and cross-links are valid.
- How to run:
  - Documentation-only; no run command needed.

---

# Task: General-Purpose LLM Documentation Templates

## Scope Guard
- [x] Documentation-only task; no runtime code or schema changes.
- [x] Capture rules already implemented in this repo and generalize them for new repositories.
- [x] Produce exactly two reusable outputs: `agents_template.md` and `documentation_rules.md`.

## Plan
- [x] Review existing policy sources (`agents.md`, `tasks/todo.md`, `tasks/lessons.md`, `docs/repo_context_llm.md`) and extract stable cross-repo rules.
- [x] Draft `agents_template.md` as a reusable template with placeholders for project-specific scope and guardrails.
- [x] Draft `documentation_rules.md` as a compact rulebook of required docs and workflow rules (including `tasks/todo.md` + `tasks/lessons.md`).
- [x] Verify both docs are consistent with current repo practices and are free of project-specific leakage where not intended.

## Data Flow
- Inputs:
  - Existing repo process docs and workflow artifacts.
- Transforms:
  - Distill repo-specific instructions into generalized, reusable standards.
- Outputs:
  - `agents_template.md`
  - `documentation_rules.md`

## Error Handling / Safety Checks
- [x] If a rule is Kalshi/NBA specific, convert it to placeholder language instead of copying literal constraints.
- [x] Keep "hard stop + re-plan" behavior for ambiguity/scope expansion in template form.

## Minimal Test Plan
- [x] Manual doc QA:
  - confirm both files exist
  - confirm required artifacts are explicitly listed (`AGENTS.md`, `tasks/todo.md`, `tasks/lessons.md`)
  - confirm workflow sequence (plan -> execute -> review -> lessons) is present

## Acceptance Criteria
- [x] `agents_template.md` can be copied into a brand-new repo with minimal edits.
- [x] `documentation_rules.md` summarizes implemented documentation/process rules in reusable form.
- [x] `tasks/todo.md` contains completion notes and run guidance for this doc task.

## Progress Notes
- Initial plan drafted and source docs reviewed (`agents.md`, `tasks/todo.md`, `tasks/lessons.md`, `docs/repo_context_llm.md`).
- Added `agents_template.md` with reusable workflow guardrails, scope controls, planning format, verification rules, and output checklist.
- Added `documentation_rules.md` summarizing required files, task lifecycle, planning standards, doc sync triggers, lessons format, and reproducibility expectations.

## Review
- What changed:
  - Added `agents_template.md` as a general-purpose AGENTS starter template with placeholders for project-specific scope and constraints.
  - Added `documentation_rules.md` summarizing reusable documentation/process rules currently practiced in this repo.
- Why:
  - To provide a copy-ready baseline for bootstrapping new repos with the same disciplined LLM workflow.
- How tested:
  - Manual doc QA.
  - Verified files exist: `Get-Item agents_template.md,documentation_rules.md`.
  - Verified key rule coverage via search (`tasks/todo.md`, `tasks/lessons.md`, workflow sequencing, scope lock, context-doc requirement).
- How to run:
  - Documentation-only deliverable; no runtime command required.
  - Reuse by copying `agents_template.md` to new repo root as `AGENTS.md`, then apply project-specific edits.
