from __future__ import annotations

import sqlite3
from pathlib import Path


def apply_reporting_views(db_path: Path | str, sql_path: Path | str) -> list[str]:
    db = Path(db_path)
    sql_file = Path(sql_path)
    sql = sql_file.read_text(encoding="utf-8")

    with sqlite3.connect(db) as conn:
        conn.executescript(sql)
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'view' AND name LIKE 'vw_mentions_%'
            ORDER BY name
            """
        ).fetchall()
    return [row[0] for row in rows]
