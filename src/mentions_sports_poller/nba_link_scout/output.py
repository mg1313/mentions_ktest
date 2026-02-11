from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def to_json_output(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def to_table_output(payload: dict[str, Any]) -> str:
    headers = ("Game ID", "Matchup", "Target", "Method", "Links", "Page URL")
    rows: list[tuple[str, str, str, str, str, str]] = []
    for item in payload.get("results", []):
        game = item.get("game", {})
        matchup = f"{game.get('away', '')} @ {game.get('home', '')}".strip()
        extraction = item.get("extraction", {})
        links = extraction.get("found_links", [])
        rows.append(
            (
                str(game.get("game_id", "")),
                matchup,
                str(item.get("target_site", "")),
                str(extraction.get("method_used", "")),
                str(len(links)),
                str(item.get("page_url", "")),
            )
        )

    return _render_table(headers=headers, rows=rows)


def _render_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    lines: list[str] = []
    lines.append(_format_row(headers, widths))
    lines.append(_format_row(tuple("-" * width for width in widths), widths))
    for row in rows:
        lines.append(_format_row(row, widths))
    if not rows:
        lines.append("(no rows)")
    return "\n".join(lines)


def _format_row(row: tuple[str, ...], widths: list[int]) -> str:
    return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row))


def update_daily_video_output_file(path: str | Path, rows: list[dict[str, Any]]) -> dict[str, int]:
    output_path = Path(path)
    existing = _load_existing_rows(output_path)
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in existing:
        key = _daily_row_key(row)
        if key is None:
            continue
        merged[key] = row
    for row in rows:
        key = _daily_row_key(row)
        if key is None:
            continue
        merged[key] = row

    merged_rows = list(merged.values())
    merged_rows.sort(key=lambda row: (str(row.get("date", "")), str(row.get("away", "")), str(row.get("home", ""))))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged_rows, indent=2, sort_keys=True), encoding="utf-8")
    return {"existing_rows": len(existing), "input_rows": len(rows), "written_rows": len(merged_rows)}


def _load_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _daily_row_key(row: dict[str, Any]) -> tuple[str, str, str] | None:
    date_value = row.get("date")
    home = row.get("home")
    away = row.get("away")
    if not isinstance(date_value, str) or not isinstance(home, str) or not isinstance(away, str):
        return None
    main_video_url = row.get("main_video_url")
    video_url = row.get("video_url")
    if main_video_url is None and video_url is None:
        return None
    return date_value, home, away
