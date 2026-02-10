from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol

from .models import Game, ScheduleSourceConfig


@dataclass(frozen=True)
class ScheduleQuery:
    requested_date: date
    start_date: date
    end_date: date


class ScheduleProvider(Protocol):
    def describe_requests(self, query: ScheduleQuery) -> list[dict[str, Any]]:
        ...

    def fetch_games(self, query: ScheduleQuery) -> list[Game]:
        ...

    def dry_run_games(self, query: ScheduleQuery) -> list[Game]:
        ...


def make_schedule_query(requested_date: date, config: ScheduleSourceConfig) -> ScheduleQuery:
    start_date = requested_date + timedelta(days=config.start_offset_days)
    end_date = requested_date + timedelta(days=config.end_offset_days)
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    return ScheduleQuery(requested_date=requested_date, start_date=start_date, end_date=end_date)


class HttpJsonScheduleProvider:
    def __init__(
        self,
        *,
        config: ScheduleSourceConfig,
        fetcher: Any | None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.fetcher = fetcher
        self.logger = logger or logging.getLogger(__name__)

    def describe_requests(self, query: ScheduleQuery) -> list[dict[str, Any]]:
        url, params = _build_schedule_request(query, self.config)
        return [{"url": url, "params": params, "headers": self.config.request_headers}]

    def fetch_games(self, query: ScheduleQuery) -> list[Game]:
        if self.fetcher is None:
            raise ValueError("http_json provider needs a fetcher for non-dry runs")
        url, params = _build_schedule_request(query, self.config)
        payload = self.fetcher.get_json(url, params=params, headers=self.config.request_headers)
        rows = _extract_rows(payload, self.config.games_path)
        return _rows_to_games(rows=rows, config=self.config)

    def dry_run_games(self, query: ScheduleQuery) -> list[Game]:
        if self.config.dry_run_games:
            return _rows_to_games(rows=list(self.config.dry_run_games), config=self.config)
        self.logger.info("dry-run has no schedule_source.dry_run_games configured")
        return []


class FileJsonScheduleProvider:
    def __init__(self, *, config: ScheduleSourceConfig) -> None:
        self.config = config

    def describe_requests(self, query: ScheduleQuery) -> list[dict[str, Any]]:
        return [{"file_path": self.config.file_path}]

    def fetch_games(self, query: ScheduleQuery) -> list[Game]:
        if not self.config.file_path:
            raise ValueError("file_path is required for file_json provider")
        path = Path(self.config.file_path)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("schedule file must contain a JSON object")
        rows = _extract_rows(payload, self.config.games_path)
        return _rows_to_games(rows=rows, config=self.config)

    def dry_run_games(self, query: ScheduleQuery) -> list[Game]:
        return self.fetch_games(query)


def make_schedule_provider(
    *,
    config: ScheduleSourceConfig,
    fetcher: Any | None,
    logger: logging.Logger | None = None,
) -> ScheduleProvider:
    if config.provider == "http_json":
        return HttpJsonScheduleProvider(config=config, fetcher=fetcher, logger=logger)
    if config.provider == "file_json":
        return FileJsonScheduleProvider(config=config)
    raise ValueError(f"unsupported schedule source provider: {config.provider}")


def _build_schedule_request(query: ScheduleQuery, config: ScheduleSourceConfig) -> tuple[str, dict[str, str]]:
    if not config.url_template:
        raise ValueError("url_template is required")
    format_vars = {
        "requested_date": query.requested_date.strftime(config.date_format),
        "start_date": query.start_date.strftime(config.date_format),
        "end_date": query.end_date.strftime(config.date_format),
        "requested_date_compact": query.requested_date.strftime("%Y%m%d"),
        "start_date_compact": query.start_date.strftime("%Y%m%d"),
        "end_date_compact": query.end_date.strftime("%Y%m%d"),
        "YYYYMMDD": query.requested_date.strftime("%Y%m%d"),
    }
    url = _expand_legacy_date_tokens(config.url_template.format_map(format_vars), format_vars)
    params = {
        key: _expand_legacy_date_tokens(value.format_map(format_vars), format_vars)
        for key, value in config.request_params.items()
    }
    return url, params


def _extract_rows(payload: dict[str, Any], path: str) -> list[dict[str, Any]]:
    value: Any = payload
    for part in path.split("."):
        part = part.strip()
        if not part:
            continue
        if isinstance(value, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise ValueError(f"path component '{part}' is not a list index") from exc
            value = value[index]
            continue
        if not isinstance(value, dict):
            raise ValueError(f"cannot traverse path '{path}'")
        value = value.get(part)
    if not isinstance(value, list):
        raise ValueError(f"games_path '{path}' did not resolve to a list")
    value = _expand_nested_games_list(value)
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _rows_to_games(rows: list[dict[str, Any]], config: ScheduleSourceConfig) -> list[Game]:
    games: list[Game] = []
    for index, row in enumerate(rows):
        date_value = _resolve_field_spec(row, config.field_map.date)
        home_value = _resolve_field_spec(row, config.field_map.home)
        away_value = _resolve_field_spec(row, config.field_map.away)
        game_id_value = _resolve_field_spec(row, config.field_map.game_id)
        if not game_id_value:
            game_id_value = f"generated-{index}-{date_value}-{away_value}-{home_value}"
        games.append(
            Game(
                date=date_value,
                home=home_value,
                away=away_value,
                game_id=game_id_value,
                raw=row,
            )
        )
    return games


def _extract_value(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        part = part.strip()
        if not part:
            continue
        if isinstance(value, list):
            index = int(part)
            value = value[index]
            continue
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _resolve_field_spec(row: dict[str, Any], spec: str) -> str:
    if "{" not in spec or "}" not in spec:
        return _stringify(_extract_value(row, spec))

    def replace(match: re.Match[str]) -> str:
        path = match.group(1).strip()
        return _stringify(_extract_value(row, path))

    rendered = re.sub(r"\{([^{}]+)\}", replace, spec)
    # Collapse repeated whitespace from missing placeholders.
    return " ".join(rendered.split())


def _expand_legacy_date_tokens(value: str, format_vars: dict[str, str]) -> str:
    # Support literal date token styles like ..._YYYYMMDD.json.
    replacements = (
        ("START_YYYYMMDD", format_vars["start_date_compact"]),
        ("END_YYYYMMDD", format_vars["end_date_compact"]),
        ("YYYYMMDD", format_vars["requested_date_compact"]),
    )
    out = value
    for token, token_value in replacements:
        out = out.replace(token, token_value)
    return out


def _expand_nested_games_list(rows: list[Any]) -> list[Any]:
    # Handle NBA full-season schedule shape: leagueSchedule.gameDates[].games[]
    if not rows:
        return rows
    all_are_buckets = True
    flattened: list[Any] = []
    for item in rows:
        if not isinstance(item, dict):
            all_are_buckets = False
            break
        games = item.get("games")
        if not isinstance(games, list):
            all_are_buckets = False
            break
        flattened.extend(games)
    if all_are_buckets:
        return flattened
    return rows
