import json
from pathlib import Path

from mentions_sports_poller.nba_link_scout.output import update_daily_video_output_file


def test_update_daily_video_output_file_merges_rows() -> None:
    output_path = Path("tests/fixtures/_daily_video_rows.json")
    try:
        output_path.write_text(
            json.dumps(
                [
                    {
                        "date": "2026-02-10",
                        "home": "Golden State Warriors",
                        "away": "San Antonio Spurs",
                        "main_video_url": "https://ok.ru/video/1",
                        "backup_video_url": "https://ok.ru/video/9",
                    }
                ]
            ),
            encoding="utf-8",
        )
        stats = update_daily_video_output_file(
            output_path,
            rows=[
                {
                    "date": "2026-02-10",
                    "home": "Golden State Warriors",
                    "away": "San Antonio Spurs",
                    "main_video_url": "https://ok.ru/video/1",
                    "backup_video_url": "https://ok.ru/video/9",
                    "source_page": "https://basketball-video.com/x",
                    "target_site": "basketball-video",
                    "method_used": "fallback",
                },
                {
                    "date": "2026-02-10",
                    "home": "Boston Celtics",
                    "away": "Miami Heat",
                    "main_video_url": "https://ok.ru/video/2",
                    "backup_video_url": "https://ok.ru/video/3",
                    "source_page": "https://basketball-video.com/y",
                    "target_site": "basketball-video",
                    "method_used": "fallback",
                },
            ],
        )
        assert stats["existing_rows"] == 1
        assert stats["written_rows"] == 2
        final_rows = json.loads(output_path.read_text(encoding="utf-8-sig"))
        assert len(final_rows) == 2
    finally:
        if output_path.exists():
            output_path.unlink()
