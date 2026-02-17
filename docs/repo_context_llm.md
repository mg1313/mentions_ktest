# Repository Context (LLM Technical Pack)

Use this file as the first-pass context for new tasks.

## Purpose

This repository contains two connected workflows:

1. Kalshi Mentions -> Sports market polling and liquidity analytics.
2. NBA game media pipeline (link discovery -> audio download -> transcription -> modeling datasets).

## Runtime Entry Points

- `mentions-sports-poller` -> `mentions_sports_poller.mentions_api.main:main`
- `nba-link-scout` -> `mentions_sports_poller.nba_link_scout.cli:main`
- `nba-audio-dl` -> `mentions_sports_poller.nba_link_scout.audio_cli:main`

## Workflow A: Mentions Poller (`src/mentions_sports_poller/mentions_api`)

### Goal

Discover in-scope Kalshi markets (Mentions + Sports), poll orderbooks, compute execution-realistic VWAP/liquidity metrics, and persist idempotently to SQLite.

### Core Flow

1. `main.py` loads env config and initializes `SQLiteStore` + `KalshiClient` + `MentionsSportsPoller`.
2. `poller.py` refreshes universe on a slower cadence, then polls active tickers per cycle.
3. `discovery.py` + `scope.py` enforce Mentions/Sports scope and title filter.
4. `orderbook.py` normalizes ladders and derives asks from complementary bids.
5. `vwap.py` computes budget-based VWAP and spread metrics.
6. `storage.py` upserts into:
   - `market_meta`
   - `orderbook_snapshot`
   - `orderbook_levels`
   - `liquidity_metrics`
7. `term_sync.py` optionally syncs new Kalshi term vocabulary into transcript modeling datasets.

### Reliability Patterns

- API pagination + retry with exponential backoff and jitter.
- Rate limiting/throttling in client.
- Per-market fail-open handling inside poll cycle.
- Idempotent writes via primary keys and `ON CONFLICT`.

## Workflow B: NBA Link Scout + Audio/Transcript Pipeline (`src/mentions_sports_poller/nba_link_scout`)

### Goal

Given a date, find NBA game replay pages from config, discover target links (including embedded/fallback extraction), maintain daily game video outputs, download audio, transcribe with game context, and build modeling datasets.

### Link Scout Flow

1. `cli.py` command: `run`, `dry-run`, `game-info`.
2. `schedule.py` fetches schedule via pluggable provider (`http_json` or `file_json`), including NBA nested season schedule flattening.
3. `game_selection.py` filters by date and optional team filter.
4. `url_builder.py` renders target URLs from templates.
5. `fetcher.py` or `playwright_fetcher.py` fetches HTML depending on config mode.
6. `link_finder.py` parses links using HTML parser + URL normalization + include/exclude/constraints.
7. `fallback.py` calls configured extractor modules when HTML-only search is insufficient.
8. `runner.py` builds:
   - `daily_video_rows`
   - `daily_video_pairs` (`main_video_url`, `backup_video_url`, `source_feed_page`)
9. `output.py` upserts daily output JSON by `(date, home, away)`.

### Audio/Transcription Flow

1. `audio_cli.py sync` builds/refreshes `nba_audio_manifest.json` from daily pairs.
2. `audio_cli.py download` fetches audio via `yt-dlp` + ffmpeg, with progress events.
3. `audio_cli.py transcribe`:
   - resolves audio by `audio_id`
   - auto-resolves game info packet by date
   - injects game packet + glossary prompt context
   - chunks long files (default 900s) with optional overlap
   - writes raw and corrected transcript text
4. `transcribe.py` includes deterministic correction pass for:
   - player names
   - commentator names
   - team nicknames
   (not city names)

### Dataset Flow

`audio_cli.py build-dataset` supports append-only incremental tables:

- `nba_game_factors.csv`: feed-level game factors keyed by `game_id` and feed identity.
- `nba_game_term_mentions.csv`: term counts per `game_id` and feed identity.
- `nba_terms_registry.json`: persistent term registry.

Important: multiple feeds for the same game are represented separately (`audio_id`, `feed_label`).

## Key Artifacts

- `data/mentions_sports.db`
- `data/nba_okru_daily.json`
- `data/nba_audio_manifest.json`
- `data/transcripts/*.json`
- `data/modeling/nba_game_factors.csv`
- `data/modeling/nba_game_term_mentions.csv`
- `data/modeling/nba_terms_registry.json`

## Test Coverage

`tests/` includes poller, retry, scope/discovery, storage idempotency, link scout URL/schedule/fetch/fallback/pairing, audio download, transcription, and incremental dataset tests.

## Maintenance Rule

When behavior changes in either workflow, update this file in the same change set.
