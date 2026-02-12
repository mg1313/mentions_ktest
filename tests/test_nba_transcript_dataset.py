from __future__ import annotations

import json
import shutil
from pathlib import Path

from mentions_sports_poller.nba_link_scout.transcript_dataset import (
    build_transcript_feature_dataset,
    load_term_definitions,
    write_dataset_outputs,
)


def test_build_transcript_feature_dataset_counts_terms_and_features() -> None:
    manifest_path = Path("tests/fixtures/_dataset_manifest.json")
    terms_path = Path("tests/fixtures/_dataset_terms.json")
    transcripts_dir = Path("tests/fixtures/_dataset_transcripts")
    game_info_dir = Path("tests/fixtures/_dataset_game_info")
    output_json = Path("tests/fixtures/_dataset_output.json")
    output_csv = Path("tests/fixtures/_dataset_output.csv")

    try:
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        game_info_dir.mkdir(parents=True, exist_ok=True)

        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "audio_id": "aaa111",
                        "date": "2026-02-09",
                        "away": "Atlanta Hawks",
                        "home": "Minnesota Timberwolves",
                        "feed_label": "main",
                        "video_url": "https://ok.ru/video/1",
                    },
                    {
                        "audio_id": "bbb222",
                        "date": "2026-02-09",
                        "away": "Atlanta Hawks",
                        "home": "Minnesota Timberwolves",
                        "feed_label": "backup",
                        "video_url": "https://ok.ru/video/2",
                    },
                ]
            ),
            encoding="utf-8",
        )
        terms_path.write_text(
            json.dumps(
                [
                    "clutch",
                    {"name": "ant-man", "pattern": r"ant[-\s]?man", "regex": True},
                ]
            ),
            encoding="utf-8",
        )
        (transcripts_dir / "aaa111.json").write_text(
            json.dumps(
                {
                    "audio_id": "aaa111",
                    "date": "2026-02-09",
                    "away": "Atlanta Hawks",
                    "home": "Minnesota Timberwolves",
                    "feed_label": "main",
                    "transcript_text": "Anthony Edwards is clutch. Ant-Man ant man ANT-MAN.",
                }
            ),
            encoding="utf-8",
        )
        (transcripts_dir / "bbb222.json").write_text(
            json.dumps(
                {
                    "audio_id": "bbb222",
                    "date": "2026-02-09",
                    "away": "Atlanta Hawks",
                    "home": "Minnesota Timberwolves",
                    "feed_label": "backup",
                    "transcript_text": "Bob Rathbun says this is clutch for the Ant-Man tonight.",
                }
            ),
            encoding="utf-8",
        )
        (transcripts_dir / "aaa111.test30s.json").write_text(
            json.dumps({"audio_id": "aaa111", "transcript_text": "test clip"}),
            encoding="utf-8",
        )
        (game_info_dir / "nba_game_info_2026-02-09.json").write_text(
            json.dumps(
                {
                    "packets": [
                        {
                            "date": "2026-02-09",
                            "away": "Atlanta Hawks",
                            "home": "Minnesota Timberwolves",
                            "rosters": {
                                "away": [{"name": "Onyeka Okongwu"}],
                                "home": [{"name": "Anthony Edwards"}],
                            },
                            "commentary": {
                                "commentators": [{"name": "Bob Rathbun"}],
                                "broadcast_teams": [
                                    {"broadcast_type": "tv", "scope": "national", "network": "ESPN"}
                                ],
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        terms = load_term_definitions(terms_file=terms_path)
        dataset = build_transcript_feature_dataset(
            transcripts_dir=transcripts_dir,
            manifest_file=manifest_path,
            game_info_dir=game_info_dir,
            terms=terms,
            include_test_transcripts=False,
        )

        assert dataset["summary"]["audio_rows"] == 2
        assert dataset["summary"]["game_rows"] == 1
        assert dataset["summary"]["errors"] == 0

        audio_rows = dataset["audio_rows"]
        row_main = next(row for row in audio_rows if row["audio_id"] == "aaa111")
        row_backup = next(row for row in audio_rows if row["audio_id"] == "bbb222")
        assert row_main["term_count__clutch"] == 1
        assert row_main["term_count__ant_man"] == 3
        assert row_main["commentator__bob_rathbun"] == 1
        assert row_main["player__anthony_edwards"] == 1
        assert row_main["is_national_tv"] is True
        assert row_main["is_local_tv"] is False
        assert row_main["tv_scope_label"] == "national"
        assert row_backup["term_count__clutch"] == 1
        assert row_backup["term_count__ant_man"] == 1

        game_row = dataset["game_rows"][0]
        assert game_row["term_count__clutch"] == 2
        assert game_row["term_count__ant_man"] == 4
        assert game_row["commentator__bob_rathbun"] == 1
        assert game_row["player__anthony_edwards"] == 1
        assert game_row["any_national_tv"] is True
        assert game_row["any_local_tv"] is False
        assert game_row["tv_scope_labels"] == "national"

        outputs = write_dataset_outputs(dataset=dataset, output_json=output_json, output_csv=output_csv)
        assert Path(outputs["json"]).exists()
        assert Path(outputs["csv"]).exists()
        assert "term_count__ant_man" in output_csv.read_text(encoding="utf-8-sig").splitlines()[0]
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if terms_path.exists():
            terms_path.unlink()
        if output_json.exists():
            output_json.unlink()
        if output_csv.exists():
            output_csv.unlink()
        if transcripts_dir.exists():
            shutil.rmtree(transcripts_dir)
        if game_info_dir.exists():
            shutil.rmtree(game_info_dir)


def test_build_transcript_feature_dataset_fail_open_on_bad_file() -> None:
    manifest_path = Path("tests/fixtures/_dataset_manifest_bad.json")
    terms_path = Path("tests/fixtures/_dataset_terms_bad.json")
    transcripts_dir = Path("tests/fixtures/_dataset_transcripts_bad")
    game_info_dir = Path("tests/fixtures/_dataset_game_info_bad")

    try:
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        game_info_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "audio_id": "ok111",
                        "date": "2026-02-10",
                        "away": "A",
                        "home": "B",
                        "feed_label": "main",
                    }
                ]
            ),
            encoding="utf-8",
        )
        terms_path.write_text(json.dumps(["term"]), encoding="utf-8")
        (transcripts_dir / "ok111.json").write_text(json.dumps({"audio_id": "ok111", "transcript_text": "term"}), encoding="utf-8")
        (transcripts_dir / "broken.json").write_text("{not-json", encoding="utf-8")
        (game_info_dir / "nba_game_info_2026-02-10.json").write_text(json.dumps({"packets": []}), encoding="utf-8")

        dataset = build_transcript_feature_dataset(
            transcripts_dir=transcripts_dir,
            manifest_file=manifest_path,
            game_info_dir=game_info_dir,
            terms=load_term_definitions(terms_file=terms_path),
        )
        assert dataset["summary"]["audio_rows"] == 1
        assert dataset["summary"]["errors"] == 1
        assert len(dataset["errors"]) == 1
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if terms_path.exists():
            terms_path.unlink()
        if transcripts_dir.exists():
            shutil.rmtree(transcripts_dir)
        if game_info_dir.exists():
            shutil.rmtree(game_info_dir)
