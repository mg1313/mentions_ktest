from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from .audio_download import download_audio_from_manifest, load_manifest_rows, sync_audio_manifest
from .transcribe import TranscriptionError, transcribe_audio_from_manifest


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)
    logger = logging.getLogger("nba_audio_dl")

    if args.command == "sync":
        stats = sync_audio_manifest(
            daily_video_file=args.daily_video_file,
            manifest_file=args.manifest,
        )
        print(json.dumps(stats, indent=2, sort_keys=True))
        return

    if args.command == "list":
        rows = load_manifest_rows(manifest_file=args.manifest, date=args.date, status=args.status)
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
            return
        print(_render_rows_table(rows))
        return

    if args.command == "download":
        progress_reporter = DownloadProgressReporter()
        stats = download_audio_from_manifest(
            manifest_file=args.manifest,
            output_dir=args.output_dir,
            audio_id=args.audio_id,
            date=args.date,
            all_pending=args.all_pending,
            force=args.force,
            logger=logger,
            progress_callback=progress_reporter.handle_event,
        )
        print(json.dumps(stats, indent=2, sort_keys=True))
        return

    if args.command == "transcribe":
        progress_reporter = TranscriptionProgressReporter()
        try:
            result = transcribe_audio_from_manifest(
                manifest_file=args.manifest,
                audio_id=args.audio_id,
                game_info_file=args.game_info_file,
                glossary_file=args.glossary_file,
                model=args.model,
                api_key_env=args.api_key_env,
                timeout_seconds=args.timeout_seconds,
                output_path=args.output,
                dry_run=args.dry_run,
                max_seconds=args.max_seconds,
                ffmpeg_bin=args.ffmpeg_bin,
                progress_callback=progress_reporter.handle_event,
            )
        except (OSError, ValueError, TranscriptionError) as exc:
            raise SystemExit(f"transcription failed: {exc}") from exc
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    raise SystemExit(f"unknown command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nba-audio-dl", description="NBA video audio download workflow")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Build/update audio manifest from daily video file")
    sync_parser.add_argument("--daily-video-file", required=True, help="Path to daily paired videos JSON")
    sync_parser.add_argument("--manifest", default="data/nba_audio_manifest.json", help="Path to audio manifest JSON")

    list_parser = subparsers.add_parser("list", help="List manifest rows")
    list_parser.add_argument("--manifest", default="data/nba_audio_manifest.json", help="Path to audio manifest JSON")
    list_parser.add_argument("--date", help="Filter date YYYY-MM-DD")
    list_parser.add_argument("--status", help="Filter status (pending/downloading/downloaded/failed)")
    list_parser.add_argument("--json", action="store_true", help="Print JSON instead of table")

    download_parser = subparsers.add_parser("download", help="Download audio files from manifest")
    download_parser.add_argument("--manifest", default="data/nba_audio_manifest.json", help="Path to audio manifest JSON")
    download_parser.add_argument("--output-dir", default="data/audio", help="Directory for audio files")
    select_group = download_parser.add_mutually_exclusive_group(required=True)
    select_group.add_argument("--audio-id", help="Download one item by audio_id")
    select_group.add_argument("--date", help="Download all items for date YYYY-MM-DD")
    select_group.add_argument("--all-pending", action="store_true", help="Download all pending entries")
    download_parser.add_argument("--force", action="store_true", help="Re-download even if already downloaded")

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe one downloaded audio file using gpt-4o-transcribe with game packet + glossary context",
    )
    transcribe_parser.add_argument("--manifest", default="data/nba_audio_manifest.json", help="Path to audio manifest JSON")
    transcribe_parser.add_argument("--audio-id", required=True, help="audio_id from the manifest")
    transcribe_parser.add_argument(
        "--game-info-file",
        required=True,
        help="Path to game info packet file produced by nba-link-scout game-info",
    )
    transcribe_parser.add_argument(
        "--glossary-file",
        default="basketball_glossary.md",
        help="Path to glossary markdown file for prompt context",
    )
    transcribe_parser.add_argument("--model", default="gpt-4o-transcribe", help="OpenAI transcription model")
    transcribe_parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable name containing OpenAI API key",
    )
    transcribe_parser.add_argument("--timeout-seconds", type=float, default=900.0, help="OpenAI request timeout in seconds")
    transcribe_parser.add_argument("--output", help="Write transcription JSON output to this path")
    transcribe_parser.add_argument(
        "--max-seconds",
        type=float,
        help="Only transcribe the first N seconds of audio (quick test mode, uses ffmpeg)",
    )
    transcribe_parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="ffmpeg binary name/path for clipping")
    transcribe_parser.add_argument("--dry-run", action="store_true", help="Build prompt/output plan without API call")

    return parser


def _configure_logging(verbose: int) -> None:
    level = logging.INFO
    if verbose >= 1:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _render_rows_table(rows: list[dict]) -> str:
    headers = ("audio_id", "date", "matchup", "feed", "status", "video_url", "audio_path")
    data: list[tuple[str, ...]] = []
    for row in rows:
        matchup = f"{row.get('away','')} @ {row.get('home','')}".strip()
        data.append(
            (
                str(row.get("audio_id", "")),
                str(row.get("date", "")),
                matchup,
                str(row.get("feed_label", "")),
                str(row.get("status", "")),
                str(row.get("video_url", "")),
                str(row.get("audio_path", "")),
            )
        )

    widths = [len(h) for h in headers]
    for row in data:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    lines: list[str] = []
    lines.append(" | ".join(headers[idx].ljust(widths[idx]) for idx in range(len(headers))))
    lines.append(" | ".join(("-" * widths[idx]) for idx in range(len(headers))))
    for row in data:
        lines.append(" | ".join(row[idx].ljust(widths[idx]) for idx in range(len(headers))))
    if not data:
        lines.append("(no rows)")
    return "\n".join(lines)


class DownloadProgressReporter:
    def __init__(self) -> None:
        self._last_bucket_by_file: dict[tuple[int, int], int] = {}
        self._last_emit_by_file: dict[tuple[int, int], float] = {}
        self._last_unknown_emit_by_file: dict[tuple[int, int], float] = {}

    def handle_event(self, event: dict) -> None:
        event_type = str(event.get("event", ""))
        index = int(event.get("index", 0))
        total_files = int(event.get("total_files", 0))
        remaining_files = int(event.get("remaining_files", 0))
        file_key = (index, total_files)
        if event_type == "file_start":
            matchup = f"{event.get('away', '')} @ {event.get('home', '')}".strip()
            print(
                f"[download] file {index}/{total_files} starting (remaining after this: {remaining_files})"
                f" | {matchup} | {event.get('feed_label', '')}",
                flush=True,
            )
            return
        if event_type == "file_done":
            print(
                f"[download] file {index}/{total_files} done (remaining files: {remaining_files})",
                flush=True,
            )
            return
        if event_type == "file_skipped":
            print(
                f"[download] file {index}/{total_files} skipped (remaining files: {remaining_files})",
                flush=True,
            )
            return
        if event_type == "file_failed":
            print(
                f"[download] file {index}/{total_files} failed (remaining files: {remaining_files})"
                f" | {event.get('error', '')}",
                flush=True,
            )
            return
        if event_type != "file_progress":
            return

        remaining_pct = event.get("remaining_percent")
        now = time.time()
        if isinstance(remaining_pct, (int, float)):
            value = max(0.0, min(100.0, float(remaining_pct)))
            bucket = int(value // 5)
            last_bucket = self._last_bucket_by_file.get(file_key)
            last_emit = self._last_emit_by_file.get(file_key, 0.0)
            if last_bucket == bucket and (now - last_emit) < 10.0:
                return
            self._last_bucket_by_file[file_key] = bucket
            self._last_emit_by_file[file_key] = now
            print(
                f"[download] file {index}/{total_files} remaining ~{value:.1f}%"
                f" | remaining files after this: {remaining_files}",
                flush=True,
            )
            return

        last_unknown = self._last_unknown_emit_by_file.get(file_key, 0.0)
        if (now - last_unknown) < 15.0:
            return
        self._last_unknown_emit_by_file[file_key] = now
        duration_seconds = event.get("duration_seconds")
        duration_text = ""
        if isinstance(duration_seconds, (int, float)) and float(duration_seconds) > 0:
            duration_text = f" | source duration ~{_format_duration(float(duration_seconds))}"
        print(
            f"[download] file {index}/{total_files} downloading (progress estimate unavailable)"
            f" | remaining files after this: {remaining_files}{duration_text}",
            flush=True,
        )


class TranscriptionProgressReporter:
    def __init__(self) -> None:
        self._last_percent = -1

    def handle_event(self, event: dict) -> None:
        if str(event.get("event", "")) != "transcription_progress":
            return
        percent_raw = event.get("percent")
        stage = str(event.get("stage", ""))
        detail = str(event.get("detail", "")).strip()
        if not isinstance(percent_raw, int):
            return
        percent = max(0, min(100, percent_raw))
        if percent < self._last_percent:
            return
        if percent == self._last_percent and not detail:
            return
        self._last_percent = percent
        suffix = f" | {detail}" if detail else ""
        print(f"[transcribe] {percent}% {stage}{suffix}", flush=True)


def _format_duration(value: float) -> str:
    total_seconds = int(value)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    return f"{minutes}m{seconds:02d}s"


if __name__ == "__main__":
    main()
