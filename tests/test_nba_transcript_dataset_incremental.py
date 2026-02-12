from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from mentions_sports_poller.nba_link_scout.transcript_dataset import (
    TermDefinition,
    build_incremental_game_term_datasets,
)


def test_incremental_game_then_term_then_game_backfill() -> None:
    base_dir = Path("tests/fixtures/_dataset_incremental")
    transcripts_dir = base_dir / "transcripts"
    game_info_dir = base_dir / "game_info"
    manifest_path = base_dir / "manifest.json"
    game_factors_path = base_dir / "game_factors.csv"
    game_term_path = base_dir / "game_terms.csv"
    registry_path = base_dir / "term_registry.json"

    try:
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        game_info_dir.mkdir(parents=True, exist_ok=True)

        _write_manifest(
            manifest_path,
            rows=[
                {
                    "audio_id": "a1",
                    "date": "2026-02-09",
                    "away": "Atlanta Hawks",
                    "home": "Minnesota Timberwolves",
                    "feed_label": "main",
                }
            ],
        )
        _write_game_info_file(
            game_info_dir / "nba_game_info_2026-02-09.json",
            packets=[
                _packet(
                    game_id="G1",
                    date="2026-02-09",
                    away="Atlanta Hawks",
                    home="Minnesota Timberwolves",
                    away_players=["Onyeka Okongwu"],
                    home_players=["Anthony Edwards"],
                    commentators=["Bob Rathbun"],
                )
            ],
        )
        _write_transcript(
            transcripts_dir / "a1.json",
            audio_id="a1",
            date="2026-02-09",
            away="Atlanta Hawks",
            home="Minnesota Timberwolves",
            text="Buzzer buzzer.",
        )

        game_result = build_incremental_game_term_datasets(
            mode="game",
            transcripts_dir=transcripts_dir,
            manifest_file=manifest_path,
            game_info_dir=game_info_dir,
            game_factors_path=game_factors_path,
            game_term_mentions_path=game_term_path,
            term_registry_path=registry_path,
        )
        assert game_result["summary"]["appended_game_rows"] == 1
        assert game_result["summary"]["appended_term_rows"] == 0

        term_result = build_incremental_game_term_datasets(
            mode="term",
            transcripts_dir=transcripts_dir,
            manifest_file=manifest_path,
            game_info_dir=game_info_dir,
            terms=[TermDefinition(name="buzzer", pattern="buzzer", is_regex=False)],
            game_factors_path=game_factors_path,
            game_term_mentions_path=game_term_path,
            term_registry_path=registry_path,
        )
        assert term_result["summary"]["appended_game_rows"] == 0
        assert term_result["summary"]["appended_term_rows"] == 1

        term_rows = _read_csv_rows(game_term_path)
        assert len(term_rows) == 1
        assert term_rows[0]["game_id"] == "G1"
        assert term_rows[0]["term"] == "buzzer"
        assert int(term_rows[0]["mention_count"]) == 2

        # Re-running same term should append nothing (append-only + dedupe key)
        term_again = build_incremental_game_term_datasets(
            mode="term",
            transcripts_dir=transcripts_dir,
            manifest_file=manifest_path,
            game_info_dir=game_info_dir,
            terms=[TermDefinition(name="buzzer", pattern="buzzer", is_regex=False)],
            game_factors_path=game_factors_path,
            game_term_mentions_path=game_term_path,
            term_registry_path=registry_path,
        )
        assert term_again["summary"]["appended_term_rows"] == 0

        # Add second game + transcript and run game mode:
        # should append new game row and backfill previously-registered term.
        _write_manifest(
            manifest_path,
            rows=[
                {
                    "audio_id": "a1",
                    "date": "2026-02-09",
                    "away": "Atlanta Hawks",
                    "home": "Minnesota Timberwolves",
                    "feed_label": "main",
                },
                {
                    "audio_id": "a2",
                    "date": "2026-02-10",
                    "away": "Chicago Bulls",
                    "home": "Boston Celtics",
                    "feed_label": "main",
                },
            ],
        )
        _write_game_info_file(
            game_info_dir / "nba_game_info_2026-02-10.json",
            packets=[
                _packet(
                    game_id="G2",
                    date="2026-02-10",
                    away="Chicago Bulls",
                    home="Boston Celtics",
                    away_players=["A"],
                    home_players=["B"],
                    commentators=["Announcer 2"],
                )
            ],
        )
        _write_transcript(
            transcripts_dir / "a2.json",
            audio_id="a2",
            date="2026-02-10",
            away="Chicago Bulls",
            home="Boston Celtics",
            text="buzzer only once",
        )

        game_again = build_incremental_game_term_datasets(
            mode="game",
            transcripts_dir=transcripts_dir,
            manifest_file=manifest_path,
            game_info_dir=game_info_dir,
            game_factors_path=game_factors_path,
            game_term_mentions_path=game_term_path,
            term_registry_path=registry_path,
        )
        assert game_again["summary"]["appended_game_rows"] == 1
        assert game_again["summary"]["appended_term_rows"] == 1

        term_rows_after = _read_csv_rows(game_term_path)
        assert len(term_rows_after) == 2
        row_g2 = next(row for row in term_rows_after if row["game_id"] == "G2")
        assert row_g2["term"] == "buzzer"
        assert int(row_g2["mention_count"]) == 1
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


def _write_manifest(path: Path, *, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def _write_game_info_file(path: Path, *, packets: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"packets": packets}), encoding="utf-8")


def _packet(
    *,
    game_id: str,
    date: str,
    away: str,
    home: str,
    away_players: list[str],
    home_players: list[str],
    commentators: list[str],
) -> dict:
    return {
        "game_id": game_id,
        "date": date,
        "away": away,
        "home": home,
        "rosters": {
            "away": [{"name": name} for name in away_players],
            "home": [{"name": name} for name in home_players],
        },
        "commentary": {
            "commentators": [{"name": name} for name in commentators],
            "broadcast_teams": [{"broadcast_type": "tv", "scope": "local", "network": "RSN"}],
        },
    }


def _write_transcript(path: Path, *, audio_id: str, date: str, away: str, home: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "audio_id": audio_id,
                "date": date,
                "away": away,
                "home": home,
                "transcript_text": text,
            }
        ),
        encoding="utf-8",
    )


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
