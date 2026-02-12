import json
from pathlib import Path

from mentions_sports_poller.nba_link_scout.audio_cli import (
    _resolve_game_info_file_for_audio_id,
)


def test_resolve_game_info_file_from_manifest_date() -> None:
    manifest_path = Path("tests/fixtures/_audio_cli_manifest.json")
    game_info_dir = Path("tests/fixtures/_audio_cli_game_info")
    game_info_path = game_info_dir / "nba_game_info_2026-02-09.json"
    try:
        game_info_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "audio_id": "abc123",
                        "date": "2026-02-09",
                        "away": "Philadelphia 76ers",
                        "home": "Portland Trail Blazers",
                        "audio_path": "data/audio/fake.mp3",
                    }
                ]
            ),
            encoding="utf-8",
        )
        game_info_path.write_text(json.dumps({"packets": []}), encoding="utf-8")

        resolved = _resolve_game_info_file_for_audio_id(
            manifest_file=manifest_path,
            audio_id="abc123",
            game_info_file_override=None,
            game_info_dir=game_info_dir,
        )
        assert Path(resolved) == game_info_path
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if game_info_path.exists():
            game_info_path.unlink()
        if game_info_dir.exists():
            game_info_dir.rmdir()


def test_resolve_game_info_file_prefers_override() -> None:
    manifest_path = Path("tests/fixtures/_audio_cli_manifest_override.json")
    override_path = Path("tests/fixtures/_audio_cli_override_game_info.json")
    try:
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "audio_id": "abc123",
                        "date": "2026-02-09",
                        "away": "Philadelphia 76ers",
                        "home": "Portland Trail Blazers",
                        "audio_path": "data/audio/fake.mp3",
                    }
                ]
            ),
            encoding="utf-8",
        )
        override_path.write_text(json.dumps({"packets": []}), encoding="utf-8")

        resolved = _resolve_game_info_file_for_audio_id(
            manifest_file=manifest_path,
            audio_id="abc123",
            game_info_file_override=str(override_path),
            game_info_dir="data",
        )
        assert Path(resolved) == override_path
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if override_path.exists():
            override_path.unlink()
