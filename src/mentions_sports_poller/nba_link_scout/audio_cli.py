from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .audio_download import download_audio_from_manifest, load_manifest_rows, sync_audio_manifest


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
        stats = download_audio_from_manifest(
            manifest_file=args.manifest,
            output_dir=args.output_dir,
            audio_id=args.audio_id,
            date=args.date,
            all_pending=args.all_pending,
            force=args.force,
            logger=logger,
        )
        print(json.dumps(stats, indent=2, sort_keys=True))
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


if __name__ == "__main__":
    main()
