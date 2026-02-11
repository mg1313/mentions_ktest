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
