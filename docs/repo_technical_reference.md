# Repository Technical Reference

This document is the detailed human-readable reference for the repository workflow and structure.

## 1) Repository Scope

Current core product scope is Kalshi Mentions -> Sports market intelligence, plus a companion NBA media/transcript pipeline used to create modeling features.

## 2) Top-Level Architecture

There are two main systems:

1. Mentions Poller (`src/mentions_sports_poller/mentions_api`)
2. NBA Link Scout and Media Pipeline (`src/mentions_sports_poller/nba_link_scout`)

Shared operational documentation lives in `RUNBOOK.md`.

## 3) System A: Mentions Poller

### 3.1 Responsibility

- Discover in-scope Mentions/Sports markets from Kalshi.
- Poll orderbook depth for active markets on schedule.
- Compute liquidity metrics with realistic depth walking (budget VWAP).
- Store market metadata and time-series market depth snapshots.
- Keep writes retry-safe and idempotent.

### 3.2 Key Modules

- `main.py`: process entrypoint.
- `config.py`: environment-driven settings object.
- `kalshi_client.py`: paginated API client with retry/throttle.
- `scope.py`: hard scope constraints (`Mentions` + `Sports`).
- `discovery.py`: universe discovery and active-set selection.
- `orderbook.py`: normalized ladder creation.
- `vwap.py`: budget-based liquidity metric calculations.
- `storage.py`: SQLite schema, indexes, and upsert persistence.
- `poller.py`: scheduler orchestration.
- `term_sync.py`: optional bridge from Kalshi terms to transcript datasets.

### 3.3 Storage Model

SQLite file (default `data/mentions_sports.db`) with:

- `market_meta`
- `orderbook_snapshot`
- `orderbook_levels`
- `liquidity_metrics`

Indexes prioritize ticker/time and side/rank query access.

### 3.4 Reliability and Runtime Behavior

- Request retry with exponential backoff + jitter.
- Request pacing/rate-limit protection.
- Universe refresh and polling loops run at separate cadences.
- One market failure does not fail full cycle.
- Poll cycle logs include active-set size and success/failure counts.

## 4) System B: NBA Link Scout + Media Pipeline

### 4.1 Responsibility

- Select games for a date.
- Build replay-page URLs from game metadata and config templates.
- Extract intermediary and final links with deterministic filtering.
- Fall back to configured external extractors when needed.
- Maintain per-game daily outputs for main/backup video feeds.
- Download audio, transcribe, and produce feed-aware modeling datasets.

### 4.2 Key Modules

- `cli.py`: link scout CLI.
- `config.py`: config parser and validation.
- `models.py`: typed dataclasses for game/config/results.
- `schedule.py`: pluggable schedule providers.
- `game_selection.py`: date/team filtering.
- `url_builder.py`: template rendering from game context.
- `fetcher.py`: HTTP fetch with retries.
- `playwright_fetcher.py`: browser-render fallback fetch mode.
- `link_finder.py`: parser + filter engine.
- `fallback.py`: adapter for user-provided extractor functions.
- `runner.py`: end-to-end orchestration and result aggregation.
- `output.py`: JSON/table rendering and daily upsert output.

Audio/transcript modules:

- `audio_cli.py`: manifest/download/transcribe/dataset commands.
- `audio_download.py`: yt-dlp download pipeline and progress.
- `transcribe.py`: OpenAI transcription integration and correction pass.
- `game_info.py`: game info packet builder (rosters/commentary metadata).
- `transcript_dataset.py`: append-only and snapshot dataset generation.

### 4.3 Config Shape and Extensibility

Main config supports:

- `schedule_source`
- `target_sites[]` with `url_templates` + `link_search_rule`
- `video_link_rule`
- ordered `fallback_extractors[]`
- `http` options including `target_page_fetch_mode` (`http`/`playwright`)

Hardcoded site assumptions are intentionally minimized; behavior is mostly config-driven.

### 4.4 Data Products

- Daily paired links: `data/nba_okru_daily.json`
- Audio manifest: `data/nba_audio_manifest.json`
- Transcripts: `data/transcripts/*.json`
- Game factors table: `data/modeling/nba_game_factors.csv`
- Game-term mentions table: `data/modeling/nba_game_term_mentions.csv`
- Term registry: `data/modeling/nba_terms_registry.json`

### 4.5 Feed-Level Representation

For a single `game_id`, multiple feeds (e.g., home/away commentary) are stored as separate rows keyed by feed identity (`audio_id`, `feed_label`) in both factors and term tables.

## 5) CLI Surfaces

- `mentions-sports-poller`:
  - default loop
  - `--once`
- `nba-link-scout`:
  - `run`
  - `dry-run`
  - `game-info`
- `nba-audio-dl`:
  - `sync`
  - `list`
  - `download`
  - `transcribe`
  - `build-dataset`

## 6) Testing

Pytest suite under `tests/` covers:

- scope/discovery
- retry behavior
- orderbook/VWAP
- storage idempotency/migrations
- link scout URL/schedule/fetch/link/fallback/pairing/output
- audio download logic
- transcription and CLI defaults
- incremental transcript dataset behavior

## 7) Operational Notes

- See `RUNBOOK.md` for commands.
- PowerShell date range runner for link scout: `scripts/run_nba_link_range.ps1`.

## 8) Documentation Synchronization

Keep these files synchronized when workflow behavior changes:

- `docs/repo_context_llm.md`
- `docs/repo_technical_reference.md`
- `docs/repo_intuition_essay.md`
- `RUNBOOK.md`
