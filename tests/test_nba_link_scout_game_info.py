from datetime import date

from mentions_sports_poller.nba_link_scout.game_info import build_game_info_packets
from mentions_sports_poller.nba_link_scout.models import (
    LinkSearchRule,
    ScheduleFieldMap,
    ScheduleSourceConfig,
    ScoutConfig,
    TargetSiteRule,
)


class FakeFetcher:
    def __init__(self, payload_by_url: dict[str, dict]) -> None:
        self.payload_by_url = payload_by_url
        self.requests: list[tuple[str, dict | None]] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        self.requests.append((url, params))
        if url not in self.payload_by_url:
            raise AssertionError(f"unexpected URL: {url}")
        return self.payload_by_url[url]


def _make_config() -> ScoutConfig:
    schedule_source = ScheduleSourceConfig(
        provider="http_json",
        url_template="https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
        games_path="leagueSchedule.gameDates",
        field_map=ScheduleFieldMap(
            game_id="gameId",
            date="gameDateEst",
            home="{homeTeam.teamCity} {homeTeam.teamName}",
            away="{awayTeam.teamCity} {awayTeam.teamName}",
        ),
    )
    target_site = TargetSiteRule(
        name="dummy",
        domain="example.com",
        url_templates=("https://example.com/{game_id}",),
        link_search_rule=LinkSearchRule(base_url=None),
    )
    return ScoutConfig(schedule_source=schedule_source, target_sites=(target_site,))


def test_build_game_info_packets_extracts_rosters_and_commentators() -> None:
    schedule_url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    box_url = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600001.json"
    fetcher = FakeFetcher(
        payload_by_url={
            schedule_url: {
                "leagueSchedule": {
                    "gameDates": [
                        {
                            "games": [
                                {
                                    "gameId": "0022600001",
                                    "gameDateEst": "2026-02-09T19:00:00Z",
                                    "homeTeam": {"teamCity": "Portland", "teamName": "Trail Blazers"},
                                    "awayTeam": {"teamCity": "Philadelphia", "teamName": "76ers"},
                                }
                            ]
                        }
                    ]
                }
            },
            box_url: {
                "game": {
                    "homeTeam": {
                        "players": [
                            {"personId": 1, "firstName": "Anfernee", "familyName": "Simons", "position": "G"},
                        ]
                    },
                    "awayTeam": {
                        "players": [
                            {"personId": 2, "firstName": "Tyrese", "familyName": "Maxey", "position": "G"},
                        ]
                    },
                    "tvBroadcasters": [
                        {
                            "displayName": "ABC",
                            "language": "English",
                            "announcers": [{"name": "Mike Breen"}, {"name": "Doris Burke"}],
                        }
                    ],
                }
            },
        }
    )
    payload = build_game_info_packets(
        config=_make_config(),
        requested_date=date(2026, 2, 9),
        fetcher=fetcher,
    )
    assert payload["games_selected"] == 1
    assert len(payload["packets"]) == 1
    packet = payload["packets"][0]
    assert packet["away"] == "Philadelphia 76ers"
    assert packet["home"] == "Portland Trail Blazers"
    assert packet["rosters"]["away"][0]["name"] == "Tyrese Maxey"
    assert packet["rosters"]["home"][0]["name"] == "Anfernee Simons"
    names = {item["name"] for item in packet["commentary"]["commentators"]}
    assert names == {"Mike Breen", "Doris Burke"}


def test_build_game_info_packets_adds_note_when_commentators_missing() -> None:
    schedule_url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    box_url = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600001.json"
    fetcher = FakeFetcher(
        payload_by_url={
            schedule_url: {
                "leagueSchedule": {
                    "gameDates": [
                        {
                            "games": [
                                {
                                    "gameId": "0022600001",
                                    "gameDateEst": "2026-02-09T19:00:00Z",
                                    "homeTeam": {"teamCity": "Portland", "teamName": "Trail Blazers"},
                                    "awayTeam": {"teamCity": "Philadelphia", "teamName": "76ers"},
                                }
                            ]
                        }
                    ]
                }
            },
            box_url: {
                "game": {
                    "homeTeam": {"players": []},
                    "awayTeam": {"players": []},
                    "tvBroadcasters": [{"displayName": "ABC", "language": "English"}],
                }
            },
        }
    )
    payload = build_game_info_packets(
        config=_make_config(),
        requested_date=date(2026, 2, 9),
        fetcher=fetcher,
    )
    packet = payload["packets"][0]
    assert packet["commentary"]["commentators"] == []
    assert packet["commentary"]["notes"]
    assert "No named commentators found" in packet["commentary"]["notes"][0]
