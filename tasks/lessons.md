# Lessons Learned

## 2026-02-10 - Market scope fields are not present on `/markets` rows
- What happened:
  - Pre-flight showed `/markets?series_ticker=...` rows can have `series_ticker`, `category`, and `tags` unset.
- Root cause:
  - Scope metadata is guaranteed at series level, not always repeated at market row level.
- Preventative rule:
  - Enforce scope using in-scope series membership and ticker prefix checks, not market-row category/tags alone.
- How to detect earlier:
  - During pre-flight, print sample keys and explicitly verify presence/absence of scope fields before parser implementation.

## 2026-02-10 - Pytest tmpdir plugin fails in this sandbox
- What happened:
  - Test runs errored on temp directory permissions during pytest setup/session cleanup.
- Root cause:
  - Sandbox environment restricts temp directory traversal expected by pytest tmpdir/cache providers.
- Preventative rule:
  - In this environment, run tests with `-p no:tmpdir -p no:cacheprovider` and keep test artifacts inside workspace paths.
- How to detect earlier:
  - Run a short pytest smoke command immediately after adding the first test that relies on temp fixtures.

## 2026-02-10 - Dry-run provider wiring must not enforce network dependencies
- What happened:
  - `nba-link-scout dry-run` initially failed for `http_json` schedule source because provider creation required an HTTP fetcher.
- Root cause:
  - The provider factory validated non-dry-run dependencies during construction rather than during fetch execution.
- Preventative rule:
  - Allow provider construction without network clients when dry-run paths can satisfy output using local plan/sample data.
- How to detect earlier:
  - Add a CLI dry-run smoke check for each supported schedule provider mode before marking implementation complete.

## 2026-02-10 - Config/schedule loaders must handle UTF-8 BOM on Windows
- What happened:
  - JSON parsing failed for config/schedule files written by PowerShell due to BOM bytes at file start.
- Root cause:
  - Loaders used `encoding="utf-8"` which does not strip BOM.
- Preventative rule:
  - Read user-provided JSON files with `utf-8-sig` for CLI-facing config/fixture inputs.
- How to detect earlier:
  - Add one test fixture saved with BOM encoding and verify loader behavior.

## 2026-02-10 - Fallback chain debug logic should not assume concrete adapter class
- What happened:
  - Unit tests using lightweight stub fallback adapters failed because runner debug fields assumed `.config` exists.
- Root cause:
  - Runtime/debug code coupled to `FallbackExtractorAdapter` internals instead of duck-typing on `extract(...)`.
- Preventative rule:
  - In orchestrators, treat adapters by interface (`extract`) and make debug metadata resilient to missing optional attributes.
- How to detect earlier:
  - Keep at least one unit test using a plain stub object with only the minimal callable surface.

## 2026-02-10 - NBA scoreboard source needs explicit schema mapping
- What happened:
  - User-provided endpoint format was valid, but default config assumed `games` at root and flat team fields.
- Root cause:
  - Source-specific JSON shape differences were not reflected in default template values.
- Preventative rule:
  - For each source template, encode known `games_path` and nested field mappings up front.
- How to detect earlier:
  - Add a dry-run check that inspects built request URL + a schema fixture for that source.

## 2026-02-10 - Full-season NBA schedule requires nested list flattening
- What happened:
  - Full-season endpoint exposes `gameDates[]` buckets containing nested `games[]`, not a direct games list.
- Root cause:
  - Parser assumed `games_path` resolves directly to rows.
- Preventative rule:
  - Flatten known nested bucket shapes (`gameDates[].games[]`) in extraction helper when configured path lands on buckets.
- How to detect earlier:
  - Add unit tests for both direct game lists and bucketed list sources.

## 2026-02-10 - Retry policy must distinguish retryable vs non-retryable HTTP statuses
- What happened:
  - 403 responses were retried repeatedly, creating noise and wasted latency without improving success.
- Root cause:
  - HTTP status handling retried all `HTTPStatusError` exceptions instead of only 429/5xx.
- Preventative rule:
  - Retry only retryable statuses (429, 5xx) plus transport/timeouts; fail fast on 4xx like 403.
- How to detect earlier:
  - Add explicit unit tests for non-retryable status behavior (e.g., 403 single-attempt assertion).

## 2026-02-10 - Fallback extraction should still run when primary page fetch fails
- What happened:
  - A blocked source page prevented all downstream extraction despite configured fallback extractors.
- Root cause:
  - Runner exited immediately on fetch exception before invoking fallback chain.
- Preventative rule:
  - If fallback extractors are configured, attempt them on the candidate URL even when HTML fetch fails.
- How to detect earlier:
  - Add a unit test with failing fetcher + successful fallback extractor and assert non-empty output.

## 2026-02-10 - WebDriver failures should trip a circuit-breaker during batch runs
- What happened:
  - Selenium fallback raised repeated fatal stacktraces for many games, adding latency/noise with no chance of recovery.
- Root cause:
  - Per-game fallback retries kept invoking the same broken extractor state.
- Preventative rule:
  - Disable a fallback adapter for the remainder of the run after fatal WebDriver-style errors (or repeated failures).
- How to detect earlier:
  - Add a unit test covering two consecutive candidates where first fatal error disables the adapter before second candidate.

## 2026-02-10 - Selenium helper should fail open instead of propagating browser init/runtime crashes
- What happened:
  - Raw Selenium exceptions leaked large stacktraces and overshadowed primary extraction flow.
- Root cause:
  - Helper raised WebDriver exceptions directly without graceful fallback behavior.
- Preventative rule:
  - In optional extractors, catch WebDriver-level exceptions and return empty results so orchestrator can continue with other paths.
- How to detect earlier:
  - Add integration smoke run with intentionally broken WebDriver and assert run completes with logged warnings, not hard errors.

## 2026-02-10 - Anti-bot sites may require browser-fetch mode at the orchestrator level
- What happened:
  - Standalone Playwright probe succeeded on `basketball-video.com` while `httpx` was consistently blocked with 403.
- Root cause:
  - Transport-level anti-bot checks differentiated scripted HTTP clients from full browser execution.
- Preventative rule:
  - Keep fetch strategy configurable (`http` vs browser mode) and scope browser mode to target pages only to avoid over-broad complexity.
- How to detect earlier:
  - Run a one-page A/B probe (`httpx` vs Playwright) before deep debugging URL/parser logic when repeated 403s appear.

## 2026-02-10 - Multi-feed outputs need provenance-aware pairing, not flat URL rows
- What happened:
  - Games frequently produced multiple OK.ru links; flat per-link rows made it unclear which two belonged to primary/backup from the same guide page.
- Root cause:
  - Output layer lacked provenance-aware grouping by extraction source page.
- Preventative rule:
  - Persist link provenance (`video_url` + `extracted_from_url`) and build per-game paired outputs that prefer same-source feed links.
- How to detect earlier:
  - Add a unit test with 3+ links from mixed source pages and assert pair selection from the preferred intermediary domain.

## 2026-02-11 - Distinct workflows should use explicit subpackages
- What happened:
  - Mentions polling modules and NBA video-link modules were colocated in the same package root, which blurred boundaries between two independent processes.
- Root cause:
  - Initial package layout optimized for speed of implementation rather than long-term workflow separation.
- Preventative rule:
  - Keep each workflow in its own explicit subpackage (`mentions_api`, `nba_link_scout`) and point CLI entrypoints directly at workflow-specific modules.
- How to detect earlier:
  - During first pass of project structure review, verify each top-level module belongs to exactly one workflow.

## 2026-02-11 - NBA boxscore broadcaster fields may omit named commentators
- What happened:
  - Commentary packet generation could not rely on consistently present announcer/commentator name fields in NBA boxscore payloads.
- Root cause:
  - Broadcaster metadata is often network/station-level and does not guarantee explicit on-air talent names.
- Preventative rule:
  - Model commentary outputs with two layers: named `commentators` when available and `broadcast_teams` fallback metadata when names are absent.
- How to detect earlier:
  - Add fixture tests for both payload shapes (with and without announcer name keys) before wiring downstream transcript attribution logic.

## 2026-02-11 - Transcript context joins should key on normalized game identity
- What happened:
  - Transcription context needs the correct game packet for each audio feed; mismatched joins would silently degrade transcription quality.
- Root cause:
  - Audio and game-info outputs are produced by separate workflows and need an explicit join contract.
- Preventative rule:
  - Join audio rows to game packets using normalized (`date`, `away`, `home`) keys and fail fast when no exact match exists.
- How to detect earlier:
  - Add unit tests that verify successful match and explicit failure on non-matching game metadata.

## 2026-02-11 - Prefer repo-local temp paths for clip artifacts in this sandbox
- What happened:
  - Tests that used OS temp directories for short-lived clip files failed with permission/cleanup errors in this environment.
- Root cause:
  - Sandbox policies can restrict temp-dir traversal/cleanup semantics outside repo-controlled paths.
- Preventative rule:
  - For transient media artifacts, create temp files under repo-local directories and explicitly clean up files after use.
- How to detect earlier:
  - Add at least one test that exercises temp-file cleanup in the same environment where pytest runs.

## 2026-02-11 - Chunking defaults must account for ffprobe availability in tests
- What happened:
  - Enabling chunk planning by default triggered ffprobe subprocess calls, which broke tests in environments without ffprobe on PATH.
- Root cause:
  - Duration probing was coupled to default transcription path rather than test-injected duration metadata.
- Preventative rule:
  - Keep duration probing injectable and set `chunk_seconds=0` in unit tests that are not explicitly validating chunking.
- How to detect earlier:
  - Add a smoke test that runs transcription flow in a no-ffprobe environment with default flags.

## 2026-02-11 - Prefer manifest-derived defaults for cross-workflow file paths
- What happened:
  - Manual `--game-info-file` path lookups were a recurring friction point and source of user mistakes.
- Root cause:
  - CLI required users to bridge two workflow outputs (audio manifest -> game info file) manually.
- Preventative rule:
  - Derive dependent file paths from manifest metadata by default and keep explicit override flags optional.
- How to detect earlier:
  - During CLI design review, list all required arguments and identify which can be inferred deterministically from existing artifacts.

## 2026-02-11 - Modeling prep should exclude transcript test clips by default
- What happened:
  - Test clip artifacts (`*.test30s.json`, `*.test60s.json`) can coexist with full transcripts and would duplicate/ skew per-game term counts if included automatically.
- Root cause:
  - Transcript output naming intentionally supports quick test runs and full runs in the same directory.
- Preventative rule:
  - Dataset builders should skip `.test` transcript files by default and expose an explicit opt-in flag to include them.
- How to detect earlier:
  - Add fixture coverage with mixed full + test transcript files and assert default row count excludes test clips.

## 2026-02-12 - Incremental datasets need explicit key-based append semantics
- What happened:
  - The new game/term dataset workflow required adding rows without replacing existing rows, while still avoiding duplicates.
- Root cause:
  - Snapshot-style rebuild logic was previously the default and did not encode persistence keys.
- Preventative rule:
  - For incremental workflows, define dedupe keys up front (`game_id` and (`game_id`,`term`)) and append only missing keys.
- How to detect earlier:
  - Add tests that run the same command multiple times and assert row counts do not increase after the first append.

## 2026-02-12 - Game-level IDs are not unique when feeds are split
- What happened:
  - A single `game_id` can have multiple transcript feeds (home/away commentary), so one-row-per-game assumptions dropped feed-level detail.
- Root cause:
  - Initial incremental schema keyed dedupe only by `game_id`.
- Preventative rule:
  - Use feed-aware keys for append-only tables: game factors keyed by (`game_id`, `audio_id|feed_label`) and term rows keyed by (`game_id`, `audio_id|feed_label`, `term`).
- How to detect earlier:
  - Add tests with two transcripts mapping to the same `game_id` and assert two rows are persisted in both tables.

## 2026-02-12 - Raw payload retention should be justified by a concrete use case
- What happened:
  - Orderbook polling stored full `raw_orderbook_json` in addition to normalized levels and metrics.
- Root cause:
  - Initial design favored maximum auditability without balancing storage growth for long-running polling.
- Preventative rule:
  - Default to normalized fields required by active queries; add raw payload retention only with explicit downstream requirements and retention policy.
- How to detect earlier:
  - Estimate weekly row/size growth before finalizing schema and flag high-volume JSON columns for review.

## 2026-02-12 - Metadata column additions need explicit SQLite migration steps
- What happened:
  - We needed to add human-readable phrasing fields to `market_meta` after databases already existed in local runs.
- Root cause:
  - `CREATE TABLE IF NOT EXISTS` does not update existing table schemas.
- Preventative rule:
  - For additive schema changes, run explicit `PRAGMA table_info` checks and `ALTER TABLE ... ADD COLUMN` migrations in startup schema setup.
- How to detect earlier:
  - Add a migration test that starts from an old schema and validates new columns appear after `create_schema()`.

## 2026-02-12 - Cross-workflow integration should reuse incremental interfaces, not duplicate pipelines
- What happened:
  - We needed Mentions polling to propagate new Kalshi terms into transcript modeling datasets.
- Root cause:
  - Workflows were separate and required a bridge, but full rebuild hooks would have been expensive and redundant.
- Preventative rule:
  - For cross-workflow connections, prefer existing incremental APIs (`mode=term`) and diff on registry state to execute only new work.
- How to detect earlier:
  - Check for existing append/incremental interfaces before designing any new orchestration path.

## 2026-02-12 - Kalshi ticker suffix is not a reliable human term key
- What happened:
  - Transcript term rows were populated with 4-character codes (e.g., `airb`, `crow`) instead of full term names.
- Root cause:
  - Integration used ticker suffix as term `name` by default and did not properly parse structured `custom_strike` values.
- Preventative rule:
  - Prefer human-readable phrase sources (`custom_strike`, subtitle fields) for term naming; use ticker suffix only as fallback.
- How to detect earlier:
  - Add regression tests that assert extracted term names are full words and that `custom_strike` dict payloads are parsed without stringified braces.

## 2026-02-16 - Legacy alias cleanup must not depend only on currently-open markets
- What happened:
  - Even after fixing term extraction, older 4-char aliases persisted in registry/term CSV when corresponding markets were no longer open.
- Root cause:
  - Alias mapping originally came only from active market payloads, so closed-market aliases had no migration source.
- Preventative rule:
  - Add registry-based alias inference from legacy pattern literals and run migration on both registry and term CSV during sync.
- How to detect earlier:
  - Add a regression test where alias rows exist in registry/CSV but active markets do not include that alias ticker.

## 2026-02-17 - Narrow market-type filters should be explicit and configurable
- What happened:
  - We needed to constrain Mentions->Sports polling further to only Professional Basketball Game contracts.
- Root cause:
  - Existing scope checks enforced category/tag but not market-type wording.
- Preventative rule:
  - Add a dedicated, config-backed discovery filter (title substring) instead of ad-hoc ticker assumptions.
- How to detect earlier:
  - Include at least one discovery test fixture with an in-scope-but-wrong-sport market title and assert it is excluded.

## 2026-02-18 - Markdown patching can fail on mixed quote encodings
- What happened:
  - A targeted patch to `tasks/todo.md` failed because existing text contained mixed quote encoding from prior edits.
- Root cause:
  - Patch context matched plain ASCII quotes, but file content had non-ASCII quote variants.
- Preventative rule:
  - For long markdown files with legacy edits, prefer section-level replace by heading marker when patch context is unstable.
- How to detect earlier:
  - Run a quick tail/read before patching and normalize non-ASCII quotes when consistency matters.
