from datetime import date

from mentions_sports_poller.nba_link_scout.models import ScheduleFieldMap, ScheduleSourceConfig
from mentions_sports_poller.nba_link_scout.schedule import (
    _build_schedule_request,
    _extract_rows,
    _rows_to_games,
    ScheduleQuery,
)


def test_build_schedule_request_supports_literal_yyyymmdd_token() -> None:
    config = ScheduleSourceConfig(
        provider="http_json",
        url_template="https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_YYYYMMDD.json",
        request_params={},
        field_map=ScheduleFieldMap(game_id="gameId", date="gameEt", home="homeTeam.teamName", away="awayTeam.teamName"),
    )
    query = ScheduleQuery(requested_date=date(2026, 2, 10), start_date=date(2026, 2, 10), end_date=date(2026, 2, 10))
    url, params = _build_schedule_request(query, config)
    assert params == {}
    assert (
        url
        == "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_20260210.json"
    )


def test_rows_to_games_supports_template_field_specs() -> None:
    config = ScheduleSourceConfig(
        provider="file_json",
        field_map=ScheduleFieldMap(
            game_id="gameId",
            date="gameEt",
            home="{homeTeam.teamCity} {homeTeam.teamName}",
            away="{awayTeam.teamCity} {awayTeam.teamName}",
        ),
    )
    rows = [
        {
            "gameId": "G1",
            "gameEt": "2026-02-10T19:00:00Z",
            "homeTeam": {"teamCity": "Portland", "teamName": "Trail Blazers"},
            "awayTeam": {"teamCity": "Philadelphia", "teamName": "76ers"},
        }
    ]
    games = _rows_to_games(rows, config)
    assert len(games) == 1
    assert games[0].home == "Portland Trail Blazers"
    assert games[0].away == "Philadelphia 76ers"


def test_extract_rows_flattens_game_dates_buckets() -> None:
    payload = {
        "leagueSchedule": {
            "gameDates": [
                {
                    "gameDate": "10/22/2025 00:00:00",
                    "games": [
                        {"gameId": "1"},
                        {"gameId": "2"},
                    ],
                },
                {
                    "gameDate": "10/23/2025 00:00:00",
                    "games": [
                        {"gameId": "3"},
                    ],
                },
            ]
        }
    }
    rows = _extract_rows(payload, "leagueSchedule.gameDates")
    assert [row["gameId"] for row in rows] == ["1", "2", "3"]
