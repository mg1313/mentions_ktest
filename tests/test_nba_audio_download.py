import json
from pathlib import Path

from mentions_sports_poller.nba_link_scout.audio_download import (
    download_audio_from_manifest,
    load_manifest_rows,
    sync_audio_manifest,
)


def test_sync_manifest_creates_stable_entries() -> None:
    daily_path = Path("tests/fixtures/_daily_pairs_audio.json")
    manifest_path = Path("tests/fixtures/_audio_manifest.json")
    try:
        daily_payload = [
            {
                "date": "2026-02-09",
                "away": "Philadelphia 76ers",
                "home": "Portland Trail Blazers",
                "main_video_url": "https://ok.ru/video/111",
                "backup_video_url": "https://ok.ru/video/222",
                "all_video_urls": ["https://ok.ru/video/111", "https://ok.ru/video/222"],
                "source_feed_page": "https://guidedesgemmes.com/x",
            }
        ]
        daily_path.write_text(json.dumps(daily_payload), encoding="utf-8")
        stats = sync_audio_manifest(daily_video_file=daily_path, manifest_file=manifest_path)
        assert stats["manifest_rows_after"] == 2

        rows = load_manifest_rows(manifest_file=manifest_path)
        assert len(rows) == 2
        assert {row["feed_label"] for row in rows} == {"main", "backup"}
        assert all(row["status"] == "pending" for row in rows)
        ids = [row["audio_id"] for row in rows]
        assert len(set(ids)) == 2
    finally:
        if daily_path.exists():
            daily_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()


def test_download_audio_for_date_updates_manifest_status() -> None:
    manifest_path = Path("tests/fixtures/_audio_manifest_download.json")
    output_dir = Path("tests/fixtures/_audio_files")
    try:
        manifest_rows = [
            {
                "audio_id": "abc123",
                "date": "2026-02-09",
                "away": "Philadelphia 76ers",
                "home": "Portland Trail Blazers",
                "feed_label": "main",
                "video_url": "https://ok.ru/video/111",
                "source_feed_page": "https://guidedesgemmes.com/x",
                "status": "pending",
                "audio_path": "",
                "downloaded_at_utc": "",
                "error": "",
            },
            {
                "audio_id": "def456",
                "date": "2026-02-09",
                "away": "Philadelphia 76ers",
                "home": "Portland Trail Blazers",
                "feed_label": "backup",
                "video_url": "https://ok.ru/video/222",
                "source_feed_page": "https://guidedesgemmes.com/x",
                "status": "pending",
                "audio_path": "",
                "downloaded_at_utc": "",
                "error": "",
            },
        ]
        manifest_path.write_text(json.dumps(manifest_rows), encoding="utf-8")

        def fake_downloader(video_url: str, output_mp3_path: Path) -> None:
            output_mp3_path.parent.mkdir(parents=True, exist_ok=True)
            output_mp3_path.write_text(f"downloaded {video_url}", encoding="utf-8")

        stats = download_audio_from_manifest(
            manifest_file=manifest_path,
            output_dir=output_dir,
            date="2026-02-09",
            all_pending=False,
            downloader=fake_downloader,
        )
        assert stats["selected"] == 2
        assert stats["downloaded"] == 2
        final_rows = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        assert all(row["status"] == "downloaded" for row in final_rows)
        assert all(Path(row["audio_path"]).exists() for row in final_rows)
    finally:
        if manifest_path.exists():
            manifest_path.unlink()
        if output_dir.exists():
            for file in output_dir.glob("*"):
                file.unlink()
            output_dir.rmdir()
