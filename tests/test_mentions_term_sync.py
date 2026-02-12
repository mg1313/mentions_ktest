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
    custom_strike: str | None = None,
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
            _market(ticker="KXNBAMENTION-26FEB10SASGSW-AIRB", custom_strike="air ball"),
            _market(ticker="KXNBAMENTION-26FEB10SASGSW-AIRB", custom_strike="airball"),
            _market(ticker="KXNBAMENTION-26FEB10SASGSW-OVER", subtitle="overrated"),
        ]
    )
    as_map = {term.name: term.pattern for term in terms}
    assert as_map["airb"] == "air ball"
    assert as_map["over"] == "overrated"


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
        json.dumps([{"name": "airb", "pattern": "air ball", "regex": False}], indent=2),
        encoding="utf-8",
    )

    result = sync_kalshi_terms_to_transcript_dataset(
        markets=[
            _market(ticker="KXNBAMENTION-26FEB10SASGSW-AIRB", custom_strike="air ball"),
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
    assert [term.name for term in calls[0]["terms"]] == ["over"]

