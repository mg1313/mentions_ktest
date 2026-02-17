from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mentions_sports_poller.mentions_api.reporting_views import apply_reporting_views


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Power BI reporting views to Mentions SQLite database.",
    )
    parser.add_argument(
        "--db-path",
        default="data/mentions_sports.db",
        help="Path to SQLite DB file (default: data/mentions_sports.db).",
    )
    parser.add_argument(
        "--sql-path",
        default="powerbi/mentions_reporting_views.sql",
        help="Path to SQL file containing reporting views.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    sql_path = Path(args.sql_path)

    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")
    if not sql_path.exists():
        raise SystemExit(f"SQL file not found: {sql_path}")

    views = apply_reporting_views(db_path=db_path, sql_path=sql_path)
    print(f"Applied reporting views to: {db_path}")
    print("Views:")
    for name in views:
        print(f"- {name}")


if __name__ == "__main__":
    main()
