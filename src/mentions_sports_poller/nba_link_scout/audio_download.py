from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def sync_audio_manifest(
    *,
    daily_video_file: str | Path,
    manifest_file: str | Path,
) -> dict[str, int]:
    daily_rows = _load_json_list(Path(daily_video_file))
    manifest_path = Path(manifest_file)
    existing_rows = _load_json_list(manifest_path)
    existing_by_id: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        audio_id = row.get("audio_id")
        if isinstance(audio_id, str) and audio_id:
            existing_by_id[audio_id] = row

    generated_entries: list[dict[str, Any]] = []
    for daily_row in daily_rows:
        generated_entries.extend(_entries_from_daily_row(daily_row))

    merged_by_id = dict(existing_by_id)
    for entry in generated_entries:
        audio_id = entry["audio_id"]
        if audio_id in merged_by_id:
            previous = merged_by_id[audio_id]
            merged_by_id[audio_id] = {
                **entry,
                "status": previous.get("status", "pending"),
                "audio_path": previous.get("audio_path", ""),
                "downloaded_at_utc": previous.get("downloaded_at_utc", ""),
                "error": previous.get("error", ""),
            }
        else:
            merged_by_id[audio_id] = {
                **entry,
                "status": "pending",
                "audio_path": "",
                "downloaded_at_utc": "",
                "error": "",
            }

    merged_rows = list(merged_by_id.values())
    merged_rows.sort(key=lambda row: (row["date"], row["away"], row["home"], row["feed_label"], row["audio_id"]))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(merged_rows, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "daily_rows": len(daily_rows),
        "manifest_rows_before": len(existing_rows),
        "manifest_rows_after": len(merged_rows),
        "new_entries": max(0, len(merged_rows) - len(existing_rows)),
    }


def load_manifest_rows(
    *,
    manifest_file: str | Path,
    date: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    rows = _load_json_list(Path(manifest_file))
    filtered: list[dict[str, Any]] = []
    for row in rows:
        row_date = str(row.get("date", ""))
        row_status = str(row.get("status", ""))
        if date is not None and row_date != date:
            continue
        if status is not None and row_status != status:
            continue
        filtered.append(row)
    return filtered


def download_audio_from_manifest(
    *,
    manifest_file: str | Path,
    output_dir: str | Path,
    audio_id: str | None = None,
    date: str | None = None,
    all_pending: bool = False,
    force: bool = False,
    logger: logging.Logger | None = None,
    downloader: Callable[[str, Path], None] | None = None,
) -> dict[str, int]:
    log = logger or logging.getLogger(__name__)
    if downloader is None:
        downloader = _download_audio_with_ytdlp

    manifest_path = Path(manifest_file)
    rows = _load_json_list(manifest_path)
    if not rows:
        return {"selected": 0, "downloaded": 0, "failed": 0, "skipped": 0}

    selected_indexes = _select_row_indexes(rows, audio_id=audio_id, date=date, all_pending=all_pending)
    if not selected_indexes:
        return {"selected": 0, "downloaded": 0, "failed": 0, "skipped": 0}

    target_output_dir = Path(output_dir)
    target_output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    skipped = 0

    for idx in selected_indexes:
        row = rows[idx]
        current_status = str(row.get("status", "pending"))
        if not force and current_status == "downloaded":
            audio_path_value = str(row.get("audio_path", ""))
            if audio_path_value and Path(audio_path_value).exists():
                skipped += 1
                continue

        video_url = str(row.get("video_url", ""))
        if not video_url:
            row["status"] = "failed"
            row["error"] = "missing video_url"
            failed += 1
            continue

        file_path = _build_audio_path(target_output_dir, row)
        row["status"] = "downloading"
        row["error"] = ""
        row["audio_path"] = str(file_path)
        _write_manifest(manifest_path, rows)
        try:
            downloader(video_url, file_path)
            row["status"] = "downloaded"
            row["downloaded_at_utc"] = _utc_now_iso()
            row["error"] = ""
            downloaded += 1
            log.info(
                "downloaded audio",
                extra={
                    "audio_id": row.get("audio_id"),
                    "video_url": video_url,
                    "audio_path": str(file_path),
                },
            )
        except Exception as exc:  # pragma: no cover - runtime behavior
            row["status"] = "failed"
            row["error"] = str(exc)
            failed += 1
            log.error(
                "audio download failed",
                extra={
                    "audio_id": row.get("audio_id"),
                    "video_url": video_url,
                    "error": str(exc),
                },
            )
        finally:
            _write_manifest(manifest_path, rows)

    return {"selected": len(selected_indexes), "downloaded": downloaded, "failed": failed, "skipped": skipped}


def _entries_from_daily_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    date = str(row.get("date", ""))
    away = str(row.get("away", ""))
    home = str(row.get("home", ""))
    source_feed_page = str(row.get("source_feed_page", ""))
    all_video_urls_raw = row.get("all_video_urls", [])
    all_video_urls: list[str] = []
    if isinstance(all_video_urls_raw, list):
        for value in all_video_urls_raw:
            if isinstance(value, str) and value:
                if value not in all_video_urls:
                    all_video_urls.append(value)

    entries: list[dict[str, Any]] = []
    ordered_candidates = [
        ("main", str(row.get("main_video_url", ""))),
        ("backup", str(row.get("backup_video_url", ""))),
    ]
    for feed_label, video_url in ordered_candidates:
        if not video_url:
            continue
        entries.append(
            {
                "audio_id": _audio_id(date, away, home, feed_label, video_url),
                "date": date,
                "away": away,
                "home": home,
                "feed_label": feed_label,
                "video_url": video_url,
                "source_feed_page": source_feed_page,
            }
        )

    extra_index = 1
    for video_url in all_video_urls:
        if any(entry["video_url"] == video_url for entry in entries):
            continue
        feed_label = f"extra_{extra_index}"
        extra_index += 1
        entries.append(
            {
                "audio_id": _audio_id(date, away, home, feed_label, video_url),
                "date": date,
                "away": away,
                "home": home,
                "feed_label": feed_label,
                "video_url": video_url,
                "source_feed_page": source_feed_page,
            }
        )
    return entries


def _audio_id(date: str, away: str, home: str, feed_label: str, video_url: str) -> str:
    payload = f"{date}|{away}|{home}|{feed_label}|{video_url}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def _build_audio_path(output_dir: Path, row: dict[str, Any]) -> Path:
    slug = (
        f"{row.get('date','')}_{_slugify(str(row.get('away','')))}_at_{_slugify(str(row.get('home','')))}"
        f"_{_slugify(str(row.get('feed_label','')))}_{row.get('audio_id','')}"
    )
    return output_dir / f"{slug}.mp3"


def _slugify(value: str) -> str:
    chars = [c.lower() if c.isalnum() else "-" for c in value.strip()]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON list in {path}")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")


def _select_row_indexes(
    rows: list[dict[str, Any]],
    *,
    audio_id: str | None,
    date: str | None,
    all_pending: bool,
) -> list[int]:
    if audio_id:
        for idx, row in enumerate(rows):
            if str(row.get("audio_id", "")) == audio_id:
                return [idx]
        return []

    selected: list[int] = []
    for idx, row in enumerate(rows):
        row_date = str(row.get("date", ""))
        row_status = str(row.get("status", "pending"))
        if date is not None and row_date != date:
            continue
        if all_pending and row_status != "pending":
            continue
        if date is None and not all_pending:
            continue
        selected.append(idx)
    return selected


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _download_audio_with_ytdlp(video_url: str, output_mp3_path: Path) -> None:
    try:
        import yt_dlp
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp") from exc

    out_base = output_mp3_path.with_suffix("")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_base) + ".%(ext)s",
        "noprogress": True,
        "quiet": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
