from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from .config import ConfigError, load_scout_config
from .models import RunOptions
from .output import to_json_output, to_table_output, update_daily_video_output_file
from .runner import run_link_scout


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)
    logger = logging.getLogger("nba_link_scout")

    try:
        config = load_scout_config(args.config)
    except (OSError, ValueError, ConfigError) as exc:
        raise SystemExit(f"failed to load config: {exc}") from exc

    requested_date = _parse_date(args.date)
    options = RunOptions(
        requested_date=requested_date,
        dry_run=(args.command == "dry-run"),
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
        daily_video_output_path_override=args.daily_video_output,
    )

    payload = run_link_scout(config=config, options=options, logger=logger)
    daily_output_path = options.daily_video_output_path_override or config.daily_video_output_path
    if daily_output_path and not options.dry_run:
        write_stats = update_daily_video_output_file(
            daily_output_path,
            payload.get("daily_video_rows", []),
        )
        logger.info("updated daily video output", extra={"path": daily_output_path, **write_stats})
    json_output = to_json_output(payload)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json_output, encoding="utf-8")
    else:
        print(json_output)

    if args.table:
        print()
        print(to_table_output(payload))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nba-link-scout", description="NBA game link discovery CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("run", "dry-run"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD")
        command_parser.add_argument("--config", required=True, help="Path to JSON config file")
        command_parser.add_argument("--output", help="Write JSON output to file")
        command_parser.add_argument("--table", action="store_true", help="Also print table output")
        command_parser.add_argument("--timeout", type=float, help="Override HTTP timeout (seconds)")
        command_parser.add_argument("--max-retries", type=int, help="Override HTTP max retries")
        command_parser.add_argument(
            "--daily-video-output",
            help="Path to JSON file updated with date/home/away/video_url rows",
        )
        command_parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity")

    return parser


def _configure_logging(verbose: int) -> None:
    level = logging.INFO
    if verbose >= 1:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"--date must be YYYY-MM-DD; got '{raw}'") from exc


if __name__ == "__main__":
    main()
