from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    cleaned = ts.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    return parsed.astimezone(timezone.utc)


def to_utc_iso(ts: datetime) -> str:
    normalized = ts.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")
