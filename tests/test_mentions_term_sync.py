import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from mentions_sports_poller.mentions_api.term_sync import (
    extract_kalshi_term_definitions,
    sync_kalshi_terms_to_transcript_dataset,
)
from mentions_sports_poller.mentions_api.time_utils import utc_now
from mentions_sports_poller.mentions_api.types import DiscoveredMarket


def _market(
    *,
    ticker: str,
    subtitle: str | None = None,
    custom_strike: object | None = None,
) -> DiscoveredMarket:
    now = utc_now()
    raw = {}
    if custom_strike is not None:
        raw["custom_strike"] = custom_strike
    return DiscoveredMarket(
        ticker=ticker,
        series_ticker="KXNBAMENTION",
        title="What will the announcers say?",
        subtitle=subtitle,
        yes_sub_title=None,
        no_sub_title=None,
        category="Mentions",
        tags=("Sports",),
        status="active",
        close_time_utc=now + timedelta(hours=1),
        created_time_utc=now,
        last_trade_price=0.4,
        volume=1,
        open_interest=1,
        raw_market=raw,
    )


def test_extract_kalshi_term_definitions_prefers_custom_strike() -> None:
    terms = extract_kalshi_term_definitions(
        [
            _market(
                ticker="KXNBAMENTION-26FEB10SASGSW-AIRB",
                custom_strike={"Word": "Airball / Airballs / Airballed"},
            ),
            _market(ticker="KXNBAMENTION-26FEB10SASGSW-OVER", subtitle="overrated"),
        ]
    )
    as_map = {term.name: term for term in terms}
    assert "airball" in as_map
    assert as_map["airball"].is_regex is True
    assert "airballs" in as_map["airball"].pattern.casefold()
    assert "airballed" in as_map["airball"].pattern.casefold()
    assert "overrated" in as_map
    assert as_map["overrated"].pattern == "overrated"


def test_sync_only_new_terms(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_incremental(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return {"summary": {"registered_terms_added": len(kwargs["terms"]), "appended_term_rows": 5}}

    monkeypatch.setattr(
        "mentions_sports_poller.mentions_api.term_sync.build_incremental_game_term_datasets",
        _fake_incremental,
    )

    registry_path = Path(f"tasks/test_term_registry_{uuid4().hex}.json")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps([{"name": "airball", "pattern": "air ball", "regex": False}], indent=2),
        encoding="utf-8",
    )

    result = sync_kalshi_terms_to_transcript_dataset(
        markets=[
            _market(
                ticker="KXNBAMENTION-26FEB10SASGSW-AIRB",
                custom_strike={"Word": "Airball / Airballs / Airballed"},
            ),
            _market(ticker="KXNBAMENTION-26FEB10SASGSW-OVER", subtitle="overrated"),
        ],
        enabled=True,
        transcripts_dir="data/transcripts",
        manifest_file="data/nba_audio_manifest.json",
        game_info_dir="data",
        game_factors_path="data/modeling/nba_game_factors.csv",
        game_term_mentions_path="data/modeling/nba_game_term_mentions.csv",
        term_registry_path=str(registry_path),
    )

    assert result["new_terms"] == 1
    assert len(calls) == 1
    assert [term.name for term in calls[0]["terms"]] == ["overrated"]


def test_sync_migrates_legacy_alias_rows(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_incremental(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return {"summary": {"registered_terms_added": len(kwargs["terms"]), "appended_term_rows": 2}}

    monkeypatch.setattr(
        "mentions_sports_poller.mentions_api.term_sync.build_incremental_game_term_datasets",
        _fake_incremental,
    )

    base = Path(f"tasks/test_term_sync_{uuid4().hex}")
    base.mkdir(parents=True, exist_ok=True)
    registry_path = base / "registry.json"
    term_csv_path = base / "terms.csv"
    game_csv_path = base / "games.csv"

    registry_path.write_text(
        json.dumps([{"name": "airb", "pattern": "{'Word': 'Airball / Airballs / Airballed'}", "regex": False}], indent=2),
        encoding="utf-8",
    )
    term_csv_path.write_text(
        (
            "audio_id,feed_label,game_id,date,away,home,term,mention_count,processed_at_utc\n"
            "a1,main,g1,2026-02-10,A,B,airb,3,2026-02-10T00:00:00+00:00\n"
        ),
        encoding="utf-8",
    )
    game_csv_path.write_text(
        (
            "audio_id,feed_label,transcript_file,video_url,source_feed_page,game_id,date,away,home,matchup,"
            "is_national_tv,is_local_tv,tv_scope_label,commentators,broadcast_networks,broadcast_scopes,"
            "players_away,players_home,players_all,roster_away_json,roster_home_json,created_at_utc\n"
            "a1,main,t.json,v,u,g1,2026-02-10,A,B,A @ B,0,0,unknown,,,,,,,,,2026-02-10T00:00:00+00:00\n"
        ),
        encoding="utf-8",
    )

    result = sync_kalshi_terms_to_transcript_dataset(
        markets=[
            _market(
                ticker="KXNBAMENTION-26FEB10SASGSW-AIRB",
                custom_strike={"Word": "Airball / Airballs / Airballed"},
            ),
        ],
        enabled=True,
        transcripts_dir="data/transcripts",
        manifest_file="data/nba_audio_manifest.json",
        game_info_dir="data",
        game_factors_path=str(game_csv_path),
        game_term_mentions_path=str(term_csv_path),
        term_registry_path=str(registry_path),
    )

    assert result["registry_alias_rows_migrated"] >= 1
    assert result["term_rows_migrated"] >= 1
    assert result["new_terms"] == 0
    assert len(calls) == 0

    registry_rows = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    assert any(row.get("name") == "airball" for row in registry_rows)
    assert not any(row.get("name") == "airb" for row in registry_rows)

    lines = term_csv_path.read_text(encoding="utf-8-sig").splitlines()
    assert any(",airball," in line for line in lines[1:])


def test_sync_infers_aliases_from_registry_patterns(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_incremental(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return {"summary": {"registered_terms_added": len(kwargs["terms"]), "appended_term_rows": 1}}

    monkeypatch.setattr(
        "mentions_sports_poller.mentions_api.term_sync.build_incremental_game_term_datasets",
        _fake_incremental,
    )

    base = Path(f"tasks/test_term_sync_registry_infer_{uuid4().hex}")
    base.mkdir(parents=True, exist_ok=True)
    registry_path = base / "registry.json"
    term_csv_path = base / "terms.csv"
    game_csv_path = base / "games.csv"

    registry_path.write_text(
        json.dumps(
            [
                {"name": "airb", "pattern": "{'Word': 'Airball / Airballs / Airballed'}", "regex": False},
                {"name": "overrated", "pattern": "overrated", "is_regex": False},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    term_csv_path.write_text(
        (
            "audio_id,feed_label,game_id,date,away,home,term,mention_count,processed_at_utc\n"
            "a1,main,g1,2026-02-10,A,B,airb,1,2026-02-10T00:00:00+00:00\n"
        ),
        encoding="utf-8",
    )
    game_csv_path.write_text(
        (
            "audio_id,feed_label,transcript_file,video_url,source_feed_page,game_id,date,away,home,matchup,"
            "is_national_tv,is_local_tv,tv_scope_label,commentators,broadcast_networks,broadcast_scopes,"
            "players_away,players_home,players_all,roster_away_json,roster_home_json,created_at_utc\n"
            "a1,main,t.json,v,u,g1,2026-02-10,A,B,A @ B,0,0,unknown,,,,,,,,,2026-02-10T00:00:00+00:00\n"
        ),
        encoding="utf-8",
    )

    result = sync_kalshi_terms_to_transcript_dataset(
        markets=[_market(ticker="KXNBAMENTION-26FEB10SASGSW-OVER", subtitle="overrated")],
        enabled=True,
        transcripts_dir="data/transcripts",
        manifest_file="data/nba_audio_manifest.json",
        game_info_dir="data",
        game_factors_path=str(game_csv_path),
        game_term_mentions_path=str(term_csv_path),
        term_registry_path=str(registry_path),
    )

    assert result["registry_alias_rows_migrated"] >= 1
    assert result["term_rows_migrated"] >= 1
    assert result["new_terms"] == 0
    assert len(calls) == 0

    registry_rows = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    assert any(row.get("name") == "airball" for row in registry_rows)
    assert not any(row.get("name") == "airb" for row in registry_rows)
