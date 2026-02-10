from __future__ import annotations

from datetime import date

from .models import Game


def filter_games_for_date(
    games: list[Game],
    *,
    requested_date: date,
    team_filter: tuple[str, ...] = (),
) -> list[Game]:
    request_date_str = requested_date.isoformat()
    normalized_teams = {token.strip().upper() for token in team_filter if token.strip()}
    selected: list[Game] = []
    for game in games:
        game_date = _normalize_date(game.date)
        if game_date != request_date_str:
            continue
        if normalized_teams and not _game_has_team(game, normalized_teams):
            continue
        selected.append(game)
    return selected


def _normalize_date(raw: str) -> str:
    if len(raw) >= 10:
        return raw[:10]
    return raw


def _game_has_team(game: Game, normalized_teams: set[str]) -> bool:
    home = game.home.upper()
    away = game.away.upper()
    return home in normalized_teams or away in normalized_teams
