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
- `orderbook_snapshot`
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

## 4. Validation Commands

Run tests:

```powershell
python -m pytest -q -p no:tmpdir -p no:cacheprovider
```

## 5. Troubleshooting

- `ModuleNotFoundError: No module named 'mentions_sports_poller'`
- Set `PYTHONPATH=src` before running module commands.

- DB written to unexpected folder
- Use absolute or repo-root-relative `SQLITE_DB_PATH` explicitly.

- Permission issues from pytest temp/cache plugins in this environment
- Use `-p no:tmpdir -p no:cacheprovider` as shown above.
