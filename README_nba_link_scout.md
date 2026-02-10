# NBA Link Scout

Config-driven CLI tool to:

1. Fetch an NBA schedule
2. Select games for a user-supplied date
3. Build target page URLs from user rules
4. Extract links from HTML
5. Fall back to a user-specified embedded-link extractor module when HTML yields no matches

## Install / Run

From repo root:

```bash
python -m mentions_sports_poller.nba_link_scout run --date 2026-02-10 --config configs/nba_link_scout.example.json
```

or via script entrypoint:

```bash
nba-link-scout run --date 2026-02-10 --config configs/nba_link_scout.example.json
```

## Commands

- `nba-link-scout run --date YYYY-MM-DD --config path/to/config.json`
- `nba-link-scout dry-run --date YYYY-MM-DD --config path/to/config.json`

Common flags:

- `--output path/to/results.json` writes machine-readable JSON
- `--table` also prints a human-readable table
- `--timeout 20` overrides HTTP timeout seconds
- `--max-retries 4` overrides retry count
- `--daily-video-output data/nba_okru_daily.json` updates a persistent JSON file with `date`, `home`, `away`, `video_url`
- `-v` enables debug logs

## Config

Example config: `configs/nba_link_scout.example.json`

Key fields:

- `schedule_source`
  - `provider`: `http_json` or `file_json`
  - `url_template` + `request_params` for HTTP provider
  - `url_template` can use either `{requested_date_compact}` or literal `YYYYMMDD` token
  - `games_path`: JSON path to the game list
  - `field_map`: map source fields -> `game_id`, `date`, `home`, `away` using dotted paths, or templates like `"{homeTeam.teamCity} {homeTeam.teamName}"`
  - `dry_run_games`: optional local game rows for dry-run without network
- `target_sites[]`
  - `url_templates`: template(s) rendered from game fields
  - Available placeholders: `game_id`, `date`, `date_only`, `year`, `month`, `day`, `day_unpadded`, `month_name`, `month_name_lower`, `month_name_short`, `month_name_short_lower`, `home`, `away`, `home_slug`, `away_slug`, `matchup_slug`
  - `required_params`: required template/context fields
  - `link_search_rule`
    - `include_patterns`: substring or `re:<regex>`
    - `exclude_patterns`: substring or `re:<regex>`
    - `collect_targets`: HTML tag attributes to collect (e.g. `a.href`, `iframe.src`)
    - `constraints`: `must_contain`, `require_same_domain`, `allowed_schemes`
- `video_link_rule` (optional)
  - final URL filter for extracted video links (for example `https://ok.ru/video/`)
- `fallback_extractors` (optional list, in order)
  - each item has `module_path`, `function_name`, `function_kwargs`
  - extractors are tried on source pages and intermediary matched links (for example `guidedesgemmes.com`)
- `daily_video_output_path` (optional)
  - JSON file that is upserted each run with `date`, `home`, `away`, `video_url`

## Output

Default output is JSON with:

- requested date
- dry-run flag
- schedule request plan
- selected games
- extraction results per game + target URL
- `daily_video_rows` (flattened rows for `date/home/away/video_url`)
- errors/debug metadata

Use `--table` to print a concise table view alongside JSON.

For the basketball-video -> guidedesgemmes -> ok.ru workflow, see:

- `configs/nba_link_scout.basketball_video.template.json`
  - Uses NBA full-season schedule endpoint (`scheduleLeagueV2.json`) and auto-flattens `leagueSchedule.gameDates[].games[]`.
