import json
import os
from pathlib import Path

from mentions_sports_poller.nba_link_scout.transcribe import (
    _build_transcription_prompt,
    _load_matching_game_packet,
    transcribe_audio_from_manifest,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def post(self, url, headers=None, data=None, files=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers or {},
                "data": data or {},
                "files": files,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.payload)


def test_load_matching_game_packet() -> None:
    game_info_path = Path("tests/fixtures/_transcribe_game_info.json")
    try:
        payload = {
            "packets": [
                {"date": "2026-02-09", "away": "Chicago Bulls", "home": "Brooklyn Nets"},
                {"date": "2026-02-09", "away": "Philadelphia 76ers", "home": "Portland Trail Blazers"},
            ]
        }
        game_info_path.write_text(json.dumps(payload), encoding="utf-8")
        packet = _load_matching_game_packet(
            game_info_file=game_info_path,
            audio_row={
                "date": "2026-02-09",
                "away": "Philadelphia 76ers",
                "home": "Portland Trail Blazers",
            },
        )
        assert packet["away"] == "Philadelphia 76ers"
        assert packet["home"] == "Portland Trail Blazers"
    finally:
        if game_info_path.exists():
            game_info_path.unlink()


def test_build_transcription_prompt_contains_packet_and_glossary() -> None:
    prompt = _build_transcription_prompt(
        audio_row={
            "date": "2026-02-09",
            "away": "Philadelphia 76ers",
            "home": "Portland Trail Blazers",
            "feed_label": "main",
        },
        game_packet={
            "date": "2026-02-09",
            "game_id": "0022600001",
            "away": "Philadelphia 76ers",
            "home": "Portland Trail Blazers",
            "rosters": {"away": [{"name": "Tyrese Maxey"}], "home": [{"name": "Anfernee Simons"}]},
            "commentary": {"commentators": [{"name": "Mike Breen"}]},
        },
        glossary_text="And-1 means continuation after a made basket while fouled.",
    )
    assert "Tyrese Maxey" in prompt
    assert "Mike Breen" in prompt
    assert "And-1 means continuation" in prompt


def test_transcribe_audio_from_manifest_writes_result() -> None:
    manifest_path = Path("tests/fixtures/_transcribe_manifest.json")
    game_info_path = Path("tests/fixtures/_transcribe_game_info_run.json")
    glossary_path = Path("tests/fixtures/_transcribe_glossary.md")
    audio_path = Path("tests/fixtures/_transcribe_audio.mp3")
    output_path = Path("tests/fixtures/_transcribe_output.json")
    try:
        audio_path.write_bytes(b"fake-audio")
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "audio_id": "abc123",
                        "audio_path": str(audio_path),
                        "away": "Philadelphia 76ers",
                        "home": "Portland Trail Blazers",
                        "date": "2026-02-09",
                        "feed_label": "main",
                        "video_url": "https://ok.ru/video/111",
                    }
                ]
            ),
            encoding="utf-8",
        )
        game_info_path.write_text(
            json.dumps(
                {
                    "packets": [
                        {
                            "date": "2026-02-09",
                            "away": "Philadelphia 76ers",
                            "home": "Portland Trail Blazers",
                            "game_id": "0022600001",
                            "rosters": {"away": [{"name": "Tyrese Maxey"}], "home": [{"name": "Anfernee Simons"}]},
                            "commentary": {"commentators": [{"name": "Mike Breen"}]},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        glossary_path.write_text("Pick and roll", encoding="utf-8")
        fake_session = FakeSession(payload={"text": "This is a transcript."})
        os.environ["DUMMY_OPENAI_KEY"] = "test-key"
        result = transcribe_audio_from_manifest(
            manifest_file=manifest_path,
            audio_id="abc123",
            game_info_file=game_info_path,
            glossary_file=glossary_path,
            output_path=output_path,
            session=fake_session,
            api_key_env="DUMMY_OPENAI_KEY",
        )
        assert result["transcript_text"] == "This is a transcript."
        assert output_path.exists()
        saved = json.loads(output_path.read_text(encoding="utf-8-sig"))
        assert saved["audio_id"] == "abc123"
        assert saved["transcript_text"] == "This is a transcript."
        assert fake_session.calls
        assert fake_session.calls[0]["data"]["model"] == "gpt-4o-transcribe"
        assert "Pick and roll" in fake_session.calls[0]["data"]["prompt"]
        assert "Tyrese Maxey" in fake_session.calls[0]["data"]["prompt"]
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if game_info_path.exists():
            game_info_path.unlink()
        if glossary_path.exists():
            glossary_path.unlink()
        if audio_path.exists():
            audio_path.unlink()
        if output_path.exists():
            output_path.unlink()
        os.environ.pop("DUMMY_OPENAI_KEY", None)


def test_transcribe_audio_max_seconds_uses_clipper_and_progress() -> None:
    manifest_path = Path("tests/fixtures/_transcribe_manifest_clip.json")
    game_info_path = Path("tests/fixtures/_transcribe_game_info_clip.json")
    glossary_path = Path("tests/fixtures/_transcribe_glossary_clip.md")
    audio_path = Path("tests/fixtures/_transcribe_audio_clip.mp3")
    output_path = Path("tests/fixtures/_transcribe_output_clip.json")
    events: list[dict] = []
    clip_calls: list[tuple[str, str, float, str]] = []
    try:
        audio_path.write_bytes(b"fake-audio-clip")
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "audio_id": "clip123",
                        "audio_path": str(audio_path),
                        "away": "Philadelphia 76ers",
                        "home": "Portland Trail Blazers",
                        "date": "2026-02-09",
                        "feed_label": "backup",
                        "video_url": "https://ok.ru/video/222",
                    }
                ]
            ),
            encoding="utf-8",
        )
        game_info_path.write_text(
            json.dumps(
                {
                    "packets": [
                        {
                            "date": "2026-02-09",
                            "away": "Philadelphia 76ers",
                            "home": "Portland Trail Blazers",
                            "game_id": "0022600001",
                            "rosters": {"away": [{"name": "Tyrese Maxey"}], "home": [{"name": "Anfernee Simons"}]},
                            "commentary": {"commentators": [{"name": "Mike Breen"}]},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        glossary_path.write_text("Transition defense", encoding="utf-8")
        fake_session = FakeSession(payload={"text": "Clip transcript."})
        os.environ["DUMMY_OPENAI_KEY"] = "test-key"

        def fake_clipper(input_path: Path, output_path: Path, max_seconds: float, ffmpeg_bin: str) -> None:
            clip_calls.append((str(input_path), str(output_path), max_seconds, ffmpeg_bin))
            output_path.write_bytes(input_path.read_bytes())

        result = transcribe_audio_from_manifest(
            manifest_file=manifest_path,
            audio_id="clip123",
            game_info_file=game_info_path,
            glossary_file=glossary_path,
            output_path=output_path,
            session=fake_session,
            api_key_env="DUMMY_OPENAI_KEY",
            max_seconds=30,
            ffmpeg_bin="ffmpeg",
            clipper=fake_clipper,
            progress_callback=lambda event: events.append(dict(event)),
        )
        assert result["transcript_text"] == "Clip transcript."
        assert result["max_seconds"] == 30.0
        assert clip_calls
        assert clip_calls[0][2] == 30
        assert clip_calls[0][3] == "ffmpeg"
        assert fake_session.calls
        file_tuple = fake_session.calls[0]["files"]["file"]
        assert "_first_30s" in str(file_tuple[0])
        percents = [event.get("percent") for event in events if event.get("event") == "transcription_progress"]
        for expected in (0, 10, 20, 30, 45, 60, 90, 100):
            assert expected in percents
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if game_info_path.exists():
            game_info_path.unlink()
        if glossary_path.exists():
            glossary_path.unlink()
        if audio_path.exists():
            audio_path.unlink()
        if output_path.exists():
            output_path.unlink()
        os.environ.pop("DUMMY_OPENAI_KEY", None)
