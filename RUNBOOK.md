# Runbook

Operational commands for the two workflows in this repository:

- `mentions-sports-poller`: Kalshi Mentions -> Sports orderbook polling + VWAP metrics.
- `nba-link-scout`: NBA schedule-driven video link discovery workflow.

## 1. Shared Setup

- Python `3.11+`
- Virtual environment at `.venv`
- Dependencies installed from `requirements.txt`

### 1.1 Environment Setup

From repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For local module execution without package install:

```powershell
$env:PYTHONPATH = "src"
```

---

## 2. Workflow A: Mentions Poller

### 3.1 Run Once

```powershell
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.mentions_api.main --once
```

If installed as script entrypoint:

```powershell
mentions-sports-poller --once
```

### 3.2 Run Continuously

```powershell
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.mentions_api.main
```

### 3.3 Key Environment Variables

- `SQLITE_DB_PATH` (default: `data/mentions_sports.db`)
- `POLL_INTERVAL_SECONDS` (default: `180`)
- `UNIVERSE_REFRESH_SECONDS` (default: `900`)
- `ACTIVE_CLOSE_WITHIN_HOURS` (default: `72`)
- `DEPTH_LEVELS_LIMIT` (default: `20`)
- `DEPTH_TARGET_NOTIONAL_DOLLARS` (default: `150`)
- `PINNED_TICKERS` (comma-separated tickers)

Example:

```powershell
$env:SQLITE_DB_PATH = "data/mentions_sports.db"
$env:POLL_INTERVAL_SECONDS = "180"
$env:UNIVERSE_REFRESH_SECONDS = "900"
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.mentions_api.main --once
```

### 3.4 Outputs

- SQLite DB: path from `SQLITE_DB_PATH`
- Tables:
- `market_meta`
- `orderbook_snapshot` (`ts_utc`, `ticker`, `last_trade_price`, `volume`, `open_interest`)
- `orderbook_levels`
- `liquidity_metrics`

---

## 3. Workflow B: NBA Link Scout

### 3.1 Playwright Prerequisites (for target page fetch mode)

Install once in your active virtualenv:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### 3.2 Run (Full Extraction)

```powershell
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.nba_link_scout run --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --daily-video-output data/nba_okru_daily.json --output data/nba_link_results_2026-02-09.json
```

```run in loop
$env:PYTHONPATH = "src"

$start = Get-Date "2026-02-01"
$end   = Get-Date "2026-02-09"

for ($d = $start; $d -le $end; $d = $d.AddDays(1)) {
    $dateStr = $d.ToString("yyyy-MM-dd")

    python -m mentions_sports_poller.nba_link_scout run `
        --date $dateStr `
        --config configs/nba_link_scout.basketball_video.template.json `
        --daily-video-output data/nba_okru_daily_$dateStr.json `
        --output data/nba_link_results_$dateStr.json
}

```

Equivalent CLI entrypoint:

```powershell
nba-link-scout run --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --daily-video-output data/nba_okru_daily.json --output data/nba_link_results_2026-02-09.json
```

### 3.3 Dry Run (No Network)

```powershell
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.nba_link_scout dry-run --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json
```

### 3.4 Common Variants

Run a single team while debugging:

```powershell
# 1) Add this in config:
# "team_filter": ["Philadelphia 76ers"]
# 2) Run normally
python -m mentions_sports_poller.nba_link_scout run --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --daily-video-output data/nba_okru_daily.json --output data/nba_link_results_2026-02-09.json
```

Verbose logs:

```powershell
python -m mentions_sports_poller.nba_link_scout run --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json -v
```

### 3.5 Where Results Are Written

- Full per-run JSON (debug + all extraction details):
  - `data/nba_link_results_YYYY-MM-DD.json`
- Daily upserted paired feed links (one row per game):
  - `data/nba_okru_daily.json`
  - Fields include:
    - `date`, `away`, `home`
    - `source_feed_page`
    - `main_video_url`
    - `backup_video_url`
    - `all_video_urls`

### 3.6 Quick Link Inspection

Show all paired links:

```powershell
Get-Content data/nba_okru_daily.json | ConvertFrom-Json | Select-Object date,away,home,main_video_url,backup_video_url
```

Show one matchup:

```powershell
Get-Content data/nba_okru_daily.json | ConvertFrom-Json | Where-Object {
  $_.away -eq "Philadelphia 76ers" -and $_.home -eq "Portland Trail Blazers"
} | Select-Object date,away,home,main_video_url,backup_video_url,source_feed_page
```

### 3.7 Date Range Runner Script

Use the script below to run `nba-link-scout` for every date in an inclusive start/end range:

- Script path: `scripts/run_nba_link_range.ps1`

Run mode:

```powershell
.\scripts\run_nba_link_range.ps1 `
  -StartDate 2026-02-09 `
  -EndDate 2026-02-12 `
  -ConfigPath configs/nba_link_scout.basketball_video.template.json `
  -DailyVideoOutputPath data/nba_okru_daily.json `
  -OutputDir data
```

Dry-run mode (no network):

```powershell
.\scripts\run_nba_link_range.ps1 `
  -StartDate 2026-02-09 `
  -EndDate 2026-02-12 `
  -ConfigPath configs/nba_link_scout.basketball_video.template.json `
  -OutputDir data `
  -DryRun
```

Optional flags:

- `-StopOnError` stop immediately if a day fails
- `-VerboseLogs` pass `-v` to `nba-link-scout`
- `-PythonExe` override interpreter path

---

## 4. Workflow C: Audio Download (Start Here for Transcription Pipeline)

This workflow consumes `data/nba_okru_daily.json` (paired video links per game) and creates a download manifest with stable IDs.

### 4.1 Build / Refresh Audio Manifest

```powershell
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.nba_link_scout.audio_cli sync --daily-video-file data/nba_okru_daily.json --manifest data/nba_audio_manifest.json
```

Equivalent entrypoint:

```powershell
nba-audio-dl sync --daily-video-file data/nba_okru_daily.json --manifest data/nba_audio_manifest.json
```

### 4.2 See What Is Pending / Downloaded

All rows:

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli list --manifest data/nba_audio_manifest.json
```

Pending for one day:

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli list --manifest data/nba_audio_manifest.json --date 2026-02-09 --status pending
```

JSON output (for scripting):

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli list --manifest data/nba_audio_manifest.json --json
```

### 4.3 Download Audio for All Games in a Day

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli download --manifest data/nba_audio_manifest.json --output-dir data/audio --date 2026-02-09
```

Progress behavior during download:

- Prints `file i/N` with remaining file count.
- Prints approximate remaining percent for the current file when available.
- If percent cannot be estimated, prints ordinal progress (`downloading file #...` style status).

### 4.4 Download One at a Time (by `audio_id`)

Find the ID from `list`, then:

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli download --manifest data/nba_audio_manifest.json --output-dir data/audio --audio-id 3f9d5b2aa1c0
```

### 4.5 Download Everything Still Pending

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli download --manifest data/nba_audio_manifest.json --output-dir data/audio --all-pending
```

### 4.6 Output / Tracking Files

- Manifest (what is pending/downloaded/failed):
  - `data/nba_audio_manifest.json`
- Audio files:
  - `data/audio/*.mp3`

Manifest row highlights:

- `audio_id` (stable, easy reference for one-at-a-time downloads)
- `date`, `away`, `home`, `feed_label` (`main`, `backup`, or `extra_n`)
- `status` (`pending`, `downloading`, `downloaded`, `failed`)
- `video_url`
- `audio_path`
- `downloaded_at_utc`
- `error`

Note:
- MP3 extraction uses `yt-dlp` with ffmpeg postprocessing. Ensure ffmpeg is available in PATH.

### 4.7 Transcribe One Audio File with GPT-4o Transcribe

Prereq:

- `OPENAI_API_KEY` set in your shell.
- A game info packet file already generated via Workflow D.

Generate game info packet file for the date if needed:

```powershell
python -m mentions_sports_poller.nba_link_scout game-info --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --output data/nba_game_info_2026-02-09.json
```

Transcribe one file by `audio_id` (auto-resolves game info file by date from manifest):

```powershell
$env:OPENAI_API_KEY = "<your-key>"
python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id 9ee9bf1cae01 --manifest data/nba_audio_manifest.json --glossary-file basketball_glossary.md
```

Long-file chunking (recommended for 2-hour audio):

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id 9ee9bf1cae01 --manifest data/nba_audio_manifest.json --glossary-file basketball_glossary.md --chunk-seconds 900 --chunk-overlap-seconds 0
```

Quick test on first 30 seconds only:

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id 9ee9bf1cae01 --manifest data/nba_audio_manifest.json --glossary-file basketball_glossary.md --max-seconds 30
```

Progress:

- Transcription CLI prints stage-based `%` updates (start -> context -> optional clipping -> API -> complete).
- Output includes both:
  - `transcript_text_raw` (pre-correction merge)
  - `transcript_text` (deterministic corrected text)
- Default output path behavior when `--output` is omitted:
  - full run: `data/transcripts/<audio_id>.json`
  - test clip (`--max-seconds N`): `data/transcripts/<audio_id>.testNs.json`
- Deterministic correction scope:
  - includes player names, commentator names, and team nicknames
  - excludes city names

Dry-run (no API call, validates matching + prompt build):

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli transcribe --audio-id 9ee9bf1cae01 --manifest data/nba_audio_manifest.json --game-info-file data/nba_game_info_2026-02-09.json --glossary-file basketball_glossary.md --dry-run
```

### 4.8 Build Modeling Dataset from Final Transcripts

`build-dataset` now supports two append-only datasets:

1. Game factors table (`game_id` + non-transcript factors):
  - teams, rosters, commentators, broadcast scope metadata
2. Game-term mentions table:
  - `game_id`, `term`, `mention_count`

Append-only outputs (defaults):
- `data/modeling/nba_game_factors.csv`
- `data/modeling/nba_game_term_mentions.csv`
- `data/modeling/nba_terms_registry.json` (terms you have run before)

Mode A: build/update game factors table

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --mode game --game-info-dir data --transcripts-dir data/transcripts --manifest data/nba_audio_manifest.json
```

Behavior:
- Appends only new `game_id` rows to game table.
- Also updates term mentions for any terms already present in the term registry (for missing `game_id`+`term` rows only).

Mode B: run one term across all previously processed games

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --mode term --term "buzzer" --game-info-dir data --transcripts-dir data/transcripts --manifest data/nba_audio_manifest.json
```

Behavior:
- Registers the term (if new) in `nba_terms_registry.json`.
- Appends missing (`game_id`,`term`) rows across games already present in game factors table.
- Existing rows are kept (no delete/reinsert).

Mode C: run multiple terms from file across all processed games

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --mode term --terms-file configs/transcript_terms.example.json --game-info-dir data --transcripts-dir data/transcripts --manifest data/nba_audio_manifest.json
```

Optional:
- `--mode both` (add game rows + apply provided terms in one call)
- `--include-test-transcripts` (include files like `*.test30s.json`)
- `--national-network ESPN --national-network TNT`
- `--game-factors-output ...`
- `--game-term-output ...`
- `--term-registry-output ...`

Snapshot mode (legacy full rebuild JSON/CSV):

```powershell
python -m mentions_sports_poller.nba_link_scout.audio_cli build-dataset --mode snapshot --terms-file configs/transcript_terms.example.json
```

---

## 5. Workflow D: NBA Game Commentary Info Packets

Build per-game packets containing:

- `date`, `game_id`, `away`, `home`
- away/home roster (from NBA boxscore payload)
- commentary metadata:
  - named `commentators` if present in NBA broadcaster-related fields
  - `broadcast_teams` network metadata fallback

Run:

```powershell
$env:PYTHONPATH = "src"
python -m mentions_sports_poller.nba_link_scout game-info --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --output data/nba_game_info_2026-02-09.json
```

Team-filtered run:

```powershell
python -m mentions_sports_poller.nba_link_scout game-info --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --team "Philadelphia 76ers" --output data/nba_game_info_2026-02-09.json
```

Dry run (no network):

```powershell
python -m mentions_sports_poller.nba_link_scout game-info --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --dry-run
```

Optional override for boxscore endpoint template:

```powershell
python -m mentions_sports_poller.nba_link_scout game-info --date 2026-02-09 --config configs/nba_link_scout.basketball_video.template.json --boxscore-url-template "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
```

---

## 6. Validation Commands

Run tests:

```powershell
python -m pytest -q -p no:tmpdir -p no:cacheprovider
```

## 7. Troubleshooting

- `ModuleNotFoundError: No module named 'mentions_sports_poller'`
- Set `PYTHONPATH=src` before running module commands.

- DB written to unexpected folder
- Use absolute or repo-root-relative `SQLITE_DB_PATH` explicitly.

- Permission issues from pytest temp/cache plugins in this environment
- Use `-p no:tmpdir -p no:cacheprovider` as shown above.
