from __future__ import annotations

import logging
import re
from contextlib import ExitStack
from datetime import date, datetime, timezone
from typing import Any

from .fetcher import HttpFetcher
from .game_selection import filter_games_for_date
from .models import ScoutConfig
from .schedule import make_schedule_provider, make_schedule_query

DEFAULT_BOXSCORE_URL_TEMPLATE = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
COMMENTATOR_KEY_MARKERS = (
    "announcer",
    "commentator",
    "commentary",
    "talent",
    "caster",
    "host",
    "playbyplay",
    "play_by_play",
    "analyst",
    "sideline",
)


def build_game_info_packets(
    *,
    config: ScoutConfig,
    requested_date: date,
    team_filter: tuple[str, ...] | None = None,
    dry_run: bool = False,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    boxscore_url_template: str = DEFAULT_BOXSCORE_URL_TEMPLATE,
    logger: logging.Logger | None = None,
    fetcher: Any | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    timeout = timeout_seconds if timeout_seconds is not None else config.http.timeout_seconds
    retries = max_retries if max_retries is not None else config.http.max_retries
    active_team_filter = config.team_filter if team_filter is None else team_filter
    query = make_schedule_query(requested_date, config.schedule_source)

    payload: dict[str, Any] = {
        "requested_date": requested_date.isoformat(),
        "dry_run": dry_run,
        "schedule_requests": [],
        "boxscore_requests": [],
        "games_total": 0,
        "games_selected": 0,
        "packets": [],
        "errors": [],
        "generated_at_utc": _utc_now_iso(),
        "commentators_source_note": (
            "Commentators are extracted from NBA boxscore broadcaster-related fields when present. "
            "If named commentators are unavailable, broadcaster network metadata is returned."
        ),
    }

    with ExitStack() as stack:
        if fetcher is None and not dry_run:
            active_fetcher = stack.enter_context(
                HttpFetcher(
                    timeout_seconds=timeout,
                    max_retries=retries,
                    backoff_base_seconds=config.http.backoff_base_seconds,
                    user_agent=config.http.user_agent,
                    request_headers=config.http.request_headers,
                    follow_redirects=config.http.follow_redirects,
                    logger=log,
                )
            )
        elif fetcher is None:
            active_fetcher = None
        else:
            active_fetcher = stack.enter_context(fetcher) if _is_context_manager(fetcher) else fetcher

        schedule_provider = make_schedule_provider(
            config=config.schedule_source,
            fetcher=None if dry_run else active_fetcher,
            logger=log,
        )
        payload["schedule_requests"] = schedule_provider.describe_requests(query)
        games = schedule_provider.dry_run_games(query) if dry_run else schedule_provider.fetch_games(query)
        selected_games = filter_games_for_date(
            games,
            requested_date=requested_date,
            team_filter=active_team_filter,
        )

        payload["games_total"] = len(games)
        payload["games_selected"] = len(selected_games)

        for game in selected_games:
            boxscore_url = boxscore_url_template.format(game_id=game.game_id)
            payload["boxscore_requests"].append({"game_id": game.game_id, "url": boxscore_url})
            if dry_run:
                payload["packets"].append(
                    {
                        "date": game.date[:10],
                        "game_id": game.game_id,
                        "away": game.away,
                        "home": game.home,
                        "boxscore_url": boxscore_url,
                        "planned_only": True,
                    }
                )
                continue

            try:
                boxscore_payload = active_fetcher.get_json(boxscore_url)
            except Exception as exc:
                message = f"failed to fetch game info for {game.game_id}: {exc}"
                payload["errors"].append(
                    {
                        "game_id": game.game_id,
                        "away": game.away,
                        "home": game.home,
                        "boxscore_url": boxscore_url,
                        "error": str(exc),
                    }
                )
                log.error(message)
                continue

            payload["packets"].append(
                _build_packet_from_boxscore(
                    game=game,
                    boxscore_url=boxscore_url,
                    payload=boxscore_payload,
                )
            )

    payload["packets"].sort(key=lambda item: (item.get("date", ""), item.get("away", ""), item.get("home", "")))
    return payload


def _build_packet_from_boxscore(*, game: Any, boxscore_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    game_payload = payload.get("game", {})
    if not isinstance(game_payload, dict):
        game_payload = {}

    away_team = game_payload.get("awayTeam", {})
    if not isinstance(away_team, dict):
        away_team = {}
    home_team = game_payload.get("homeTeam", {})
    if not isinstance(home_team, dict):
        home_team = {}

    away_roster = _extract_team_roster(away_team)
    home_roster = _extract_team_roster(home_team)
    broadcast_entries = _extract_broadcast_entries(game_payload)
    commentators = _extract_commentators(broadcast_entries)
    notes: list[str] = []
    if not commentators:
        notes.append("No named commentators found; broadcaster network metadata returned instead.")

    return {
        "date": game.date[:10],
        "game_id": game.game_id,
        "away": game.away,
        "home": game.home,
        "boxscore_url": boxscore_url,
        "rosters": {
            "away": away_roster,
            "home": home_roster,
        },
        "commentary": {
            "commentators": commentators,
            "broadcast_teams": broadcast_entries,
            "notes": notes,
        },
    }


def _extract_team_roster(team_payload: dict[str, Any]) -> list[dict[str, Any]]:
    players = team_payload.get("players", [])
    if not isinstance(players, list):
        return []
    roster: list[dict[str, Any]] = []
    for player in players:
        if not isinstance(player, dict):
            continue
        name = _first_non_empty_str(
            player.get("name"),
            _build_name(
                player.get("firstName"),
                player.get("familyName"),
            ),
            _build_name(
                player.get("first_name"),
                player.get("last_name"),
            ),
            player.get("playerName"),
        )
        roster.append(
            {
                "player_id": _stringify(player.get("personId") or player.get("playerId")),
                "name": name,
                "position": _first_non_empty_str(
                    player.get("position"),
                    player.get("pos"),
                    player.get("positionName"),
                ),
                "jersey": _stringify(
                    player.get("jerseyNum")
                    or player.get("jersey")
                    or player.get("jerseyNumber")
                ),
                "starter": bool(player.get("starter", False)),
            }
        )
    roster.sort(key=lambda row: (row.get("name", ""), row.get("player_id", "")))
    return roster


def _extract_broadcast_entries(game_payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key, value in game_payload.items():
        if "broadcaster" not in key.lower():
            continue
        entries.extend(
            _flatten_broadcast_container(
                value=value,
                source_path=f"game.{key}",
                broadcast_type=_infer_broadcast_type_from_path(f"game.{key}"),
                scope_hint="",
            )
        )
    entries.sort(
        key=lambda row: (
            row.get("broadcast_type", ""),
            row.get("scope", ""),
            row.get("network", ""),
            row.get("source_path", ""),
        )
    )
    return entries


def _flatten_broadcast_container(
    *,
    value: Any,
    source_path: str,
    broadcast_type: str,
    scope_hint: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, list):
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                continue
            out.append(
                _normalize_broadcast_entry(
                    item=item,
                    source_path=f"{source_path}[{idx}]",
                    broadcast_type=broadcast_type,
                    scope=scope_hint,
                )
            )
        return out

    if isinstance(value, dict):
        for key, nested in value.items():
            nested_scope = _stringify(key)
            nested_type = broadcast_type or _infer_broadcast_type_from_path(f"{source_path}.{key}")
            if isinstance(nested, dict):
                out.append(
                    _normalize_broadcast_entry(
                        item=nested,
                        source_path=f"{source_path}.{key}",
                        broadcast_type=nested_type,
                        scope=scope_hint or nested_scope,
                    )
                )
                continue
            out.extend(
                _flatten_broadcast_container(
                    value=nested,
                    source_path=f"{source_path}.{key}",
                    broadcast_type=nested_type,
                    scope_hint=scope_hint or nested_scope,
                )
            )
    return out


def _normalize_broadcast_entry(
    *,
    item: dict[str, Any],
    source_path: str,
    broadcast_type: str,
    scope: str,
) -> dict[str, Any]:
    entry_scope = _first_non_empty_str(
        item.get("scope"),
        item.get("market"),
        item.get("type"),
        scope,
    )
    network = _first_non_empty_str(
        item.get("displayName"),
        item.get("shortName"),
        item.get("name"),
        item.get("network"),
        item.get("station"),
        item.get("callSign"),
    )
    language = _first_non_empty_str(item.get("language"), item.get("lang"))
    return {
        "source_path": source_path,
        "broadcast_type": broadcast_type or "unknown",
        "scope": entry_scope or "unknown",
        "network": network,
        "language": language,
        "raw": item,
    }


def _extract_commentators(broadcast_entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in broadcast_entries:
        raw = entry.get("raw")
        if not isinstance(raw, dict):
            continue
        source_path = _stringify(entry.get("source_path"))
        for name, relative_path in _extract_commentator_names_from_dict(raw):
            key = (name, source_path)
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "name": name,
                    "source_path": f"{source_path}{relative_path}",
                    "broadcast_type": _stringify(entry.get("broadcast_type")),
                    "scope": _stringify(entry.get("scope")),
                    "network": _stringify(entry.get("network")),
                }
            )
    found.sort(key=lambda row: (row["name"], row["source_path"]))
    return found


def _extract_commentator_names_from_dict(payload: dict[str, Any]) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_lower = key.lower()
                next_path = f"{path}.{key}" if path else f".{key}"
                if any(marker in key_lower for marker in COMMENTATOR_KEY_MARKERS):
                    for name in _extract_names(nested):
                        names.append((name, next_path))
                visit(nested, next_path)
            return
        if isinstance(value, list):
            for idx, nested in enumerate(value):
                visit(nested, f"{path}[{idx}]")

    visit(payload, "")
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for name, path in names:
        key = (name, path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((name, path))
    return deduped


def _extract_names(value: Any) -> list[str]:
    names: list[str] = []
    if isinstance(value, str):
        raw_parts = re.split(r",|;|\|| and ", value)
        for part in raw_parts:
            normalized = _normalize_name(part)
            if normalized:
                names.append(normalized)
        return names
    if isinstance(value, dict):
        direct_name = _first_non_empty_str(
            value.get("name"),
            value.get("displayName"),
            _build_name(value.get("firstName"), value.get("lastName")),
            _build_name(value.get("first_name"), value.get("last_name")),
        )
        if direct_name:
            names.append(direct_name)
            return names
        for nested in value.values():
            names.extend(_extract_names(nested))
        return names
    if isinstance(value, list):
        for item in value:
            names.extend(_extract_names(item))
        return names
    return names


def _infer_broadcast_type_from_path(path: str) -> str:
    lower = path.lower()
    if "radio" in lower:
        return "radio"
    if "tv" in lower:
        return "tv"
    return "other"


def _first_non_empty_str(*values: Any) -> str:
    for value in values:
        text = _stringify(value).strip()
        if text:
            return text
    return ""


def _build_name(first: Any, last: Any) -> str:
    first_text = _stringify(first).strip()
    last_text = _stringify(last).strip()
    merged = f"{first_text} {last_text}".strip()
    return merged


def _normalize_name(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return ""
    if len(text) <= 2:
        return ""
    return text


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_context_manager(value: Any) -> bool:
    return hasattr(value, "__enter__") and hasattr(value, "__exit__")
