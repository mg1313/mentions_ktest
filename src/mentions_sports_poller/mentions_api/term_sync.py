from __future__ import annotations

import csv
import json
import logging
import re
import ast
from pathlib import Path
from typing import Any

from mentions_sports_poller.nba_link_scout.transcript_dataset import (
    TermDefinition,
    build_incremental_game_term_datasets,
)

from .types import DiscoveredMarket

_GENERIC_VALUES = {"", "yes", "no", "n/a", "na", "none", "null"}


def sync_kalshi_terms_to_transcript_dataset(
    *,
    markets: list[DiscoveredMarket],
    enabled: bool,
    transcripts_dir: str,
    manifest_file: str,
    game_info_dir: str,
    game_factors_path: str,
    game_term_mentions_path: str,
    term_registry_path: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    if not enabled:
        return {"enabled": False, "kalshi_terms_seen": 0, "new_terms": 0}

    kalshi_terms, alias_map = _extract_terms_and_aliases(markets)
    if not kalshi_terms:
        return {"enabled": True, "kalshi_terms_seen": 0, "new_terms": 0}

    inferred_aliases = _infer_aliases_from_registry(
        term_registry_path=Path(term_registry_path),
        logger=log,
    )
    merged_aliases = dict(alias_map)
    for key, value in inferred_aliases.items():
        merged_aliases.setdefault(key, value)

    migration = _apply_alias_migrations(
        alias_to_canonical=merged_aliases,
        term_registry_path=Path(term_registry_path),
        game_term_mentions_path=Path(game_term_mentions_path),
        logger=log,
    )

    registry_names = _load_registry_term_names(Path(term_registry_path), logger=log)
    new_terms = [
        term for term in kalshi_terms if term.name.casefold() not in registry_names
    ]
    if not new_terms:
        return {
            "enabled": True,
            "kalshi_terms_seen": len(kalshi_terms),
            "new_terms": 0,
            **migration,
        }

    result = build_incremental_game_term_datasets(
        mode="term",
        transcripts_dir=transcripts_dir,
        manifest_file=manifest_file,
        game_info_dir=game_info_dir,
        terms=new_terms,
        game_factors_path=game_factors_path,
        game_term_mentions_path=game_term_mentions_path,
        term_registry_path=term_registry_path,
        logger=log,
    )
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    return {
        "enabled": True,
        "kalshi_terms_seen": len(kalshi_terms),
        "new_terms": len(new_terms),
        "registered_terms_added": int(summary.get("registered_terms_added", 0)),
        "appended_term_rows": int(summary.get("appended_term_rows", 0)),
        **migration,
    }


def extract_kalshi_term_definitions(
    markets: list[DiscoveredMarket],
) -> list[TermDefinition]:
    terms, _ = _extract_terms_and_aliases(markets)
    return terms


def _extract_terms_and_aliases(
    markets: list[DiscoveredMarket],
) -> tuple[list[TermDefinition], dict[str, str]]:
    by_name: dict[str, TermDefinition] = {}
    alias_to_canonical: dict[str, str] = {}
    for market in markets:
        suffix_term = _term_name_from_ticker(market.ticker)
        variants = _extract_human_variants(market)
        if variants:
            term_name = _canonical_term_name(variants[0])
            pattern, is_regex = _build_pattern_from_variants(variants)
            if suffix_term and suffix_term.casefold() != term_name.casefold():
                alias_to_canonical.setdefault(suffix_term.casefold(), term_name)
        else:
            term_name = suffix_term
            if not term_name:
                continue
            pattern = term_name
            is_regex = False
        key = term_name.casefold()
        by_name.setdefault(
            key,
            TermDefinition(name=term_name, pattern=pattern, is_regex=is_regex),
        )
    return ([by_name[key] for key in sorted(by_name.keys())], alias_to_canonical)


def _term_name_from_ticker(ticker: str) -> str | None:
    if "-" not in ticker:
        return None
    suffix = ticker.rsplit("-", 1)[-1].strip().lower()
    return suffix or None


def _extract_human_variants(market: DiscoveredMarket) -> list[str]:
    raw_market = market.raw_market if isinstance(market.raw_market, dict) else {}
    collected: list[str] = []
    collected.extend(_extract_custom_strike_variants(raw_market.get("custom_strike")))
    for candidate in (
        market.subtitle,
        raw_market.get("subtitle"),
        market.yes_sub_title,
        market.no_sub_title,
    ):
        text = _normalize_text(candidate)
        if not text:
            continue
        collected.extend(_split_phrase_variants(text))

    deduped: list[str] = []
    seen: set[str] = set()
    for value in collected:
        normalized = _normalize_text(value)
        if not normalized:
            continue
        if normalized.casefold() in _GENERIC_VALUES:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _extract_custom_strike_variants(value: Any) -> list[str]:
    # Kalshi custom_strike can be a dict, e.g. {"Word": "Airball / Airballs / Airballed"}.
    if value is None:
        return []
    if isinstance(value, str):
        text = _normalize_text(value)
        if not text:
            return []
        return _split_phrase_variants(text)
    if isinstance(value, dict):
        values: list[str] = []
        preferred = ("Word", "word", "Label", "label", "Value", "value")
        for key in preferred:
            if key in value:
                text = _normalize_text(value.get(key))
                if text:
                    values.extend(_split_phrase_variants(text))
        if values:
            return values
        # Fallback: any dict string value.
        for raw in value.values():
            text = _normalize_text(raw)
            if text:
                values.extend(_split_phrase_variants(text))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_extract_custom_strike_variants(item))
        return values
    return []


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.strip("\"'")
    return " ".join(text.split())


def _split_phrase_variants(text: str) -> list[str]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return []
    # Common Kalshi phrasing uses "/" to indicate variant terms.
    parts = re.split(r"\s*/\s*", cleaned)
    variants: list[str] = []
    for part in parts:
        value = _normalize_text(part)
        if value:
            variants.append(value)
    return variants or [cleaned]


def _canonical_term_name(value: str) -> str:
    text = _normalize_text(value) or ""
    text = text.casefold()
    text = re.sub(r"[^\w\s.\-']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "term"


def _build_pattern_from_variants(variants: list[str]) -> tuple[str, bool]:
    if not variants:
        return ("", False)
    if len(variants) == 1:
        return (variants[0], False)
    pieces = [re.escape(item).replace(r"\ ", r"\s+") for item in variants]
    pattern = rf"(?<!\w)(?:{'|'.join(pieces)})(?!\w)"
    return (pattern, True)


def _apply_alias_migrations(
    *,
    alias_to_canonical: dict[str, str],
    term_registry_path: Path,
    game_term_mentions_path: Path,
    logger: logging.Logger,
) -> dict[str, int]:
    if not alias_to_canonical:
        return {
            "registry_alias_rows_migrated": 0,
            "term_rows_migrated": 0,
        }
    registry_changes = _migrate_registry_aliases(
        alias_to_canonical=alias_to_canonical,
        term_registry_path=term_registry_path,
        logger=logger,
    )
    term_row_changes = _migrate_term_csv_aliases(
        alias_to_canonical=alias_to_canonical,
        game_term_mentions_path=game_term_mentions_path,
        logger=logger,
    )
    return {
        "registry_alias_rows_migrated": registry_changes,
        "term_rows_migrated": term_row_changes,
    }


def _migrate_registry_aliases(
    *,
    alias_to_canonical: dict[str, str],
    term_registry_path: Path,
    logger: logging.Logger,
) -> int:
    if not term_registry_path.exists():
        return 0
    try:
        payload = json.loads(term_registry_path.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.warning("failed parsing term registry for alias migration", extra={"path": str(term_registry_path)})
        return 0
    if not isinstance(payload, list):
        return 0

    changed_rows = 0
    merged_by_name: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        target = alias_to_canonical.get(name.casefold(), name)
        pattern_migration = _legacy_pattern_literal_to_definition(str(item.get("pattern", "")))
        if pattern_migration is not None and target.casefold() == name.casefold():
            target = pattern_migration.name
        if target.casefold() != name.casefold():
            changed_rows += 1
        merged = dict(item)
        merged["name"] = target
        if pattern_migration is not None:
            merged["pattern"] = pattern_migration.pattern
            merged["is_regex"] = pattern_migration.is_regex
            merged.pop("regex", None)
        key = target.casefold()
        existing = merged_by_name.get(key)
        if existing is None:
            merged_by_name[key] = merged
            continue
        # Prefer regex-capable entries if there is a conflict.
        existing_regex = bool(existing.get("is_regex", existing.get("regex", False)))
        merged_regex = bool(merged.get("is_regex", merged.get("regex", False)))
        if merged_regex and not existing_regex:
            merged_by_name[key] = merged
        elif not existing_regex and not merged_regex:
            existing_pattern_len = len(str(existing.get("pattern", "")))
            merged_pattern_len = len(str(merged.get("pattern", "")))
            if merged_pattern_len > existing_pattern_len:
                merged_by_name[key] = merged

    normalized = list(merged_by_name.values())
    normalized.sort(key=lambda row: str(row.get("name", "")).casefold())
    if normalized != payload:
        term_registry_path.write_text(
            json.dumps(normalized, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return changed_rows


def _migrate_term_csv_aliases(
    *,
    alias_to_canonical: dict[str, str],
    game_term_mentions_path: Path,
    logger: logging.Logger,
) -> int:
    if not game_term_mentions_path.exists():
        return 0
    try:
        with game_term_mentions_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            fieldnames = list(reader.fieldnames or [])
    except Exception:
        logger.warning("failed reading term mentions CSV for alias migration", extra={"path": str(game_term_mentions_path)})
        return 0

    changed_rows = 0
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for row in rows:
        original = str(row.get("term", "")).strip()
        canonical = alias_to_canonical.get(original.casefold(), original)
        if canonical.casefold() != original.casefold():
            row["term"] = canonical
            changed_rows += 1
        key = (
            str(row.get("game_id", "")).strip(),
            _coalesce_text(str(row.get("audio_id", "")), str(row.get("feed_label", ""))).casefold(),
            str(row.get("term", "")).strip().casefold(),
        )
        if key not in deduped:
            deduped[key] = row
            order.append(key)
            continue
        existing = deduped[key]
        if _row_is_better(row, existing):
            deduped[key] = row

    rebuilt = [deduped[key] for key in order]
    if changed_rows > 0:
        with game_term_mentions_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rebuilt:
                writer.writerow(row)
    return changed_rows


def _coalesce_text(*values: str) -> str:
    for value in values:
        text = value.strip()
        if text:
            return text
    return ""


def _row_is_better(new_row: dict[str, Any], old_row: dict[str, Any]) -> bool:
    new_ts = str(new_row.get("processed_at_utc", ""))
    old_ts = str(old_row.get("processed_at_utc", ""))
    if new_ts > old_ts:
        return True
    if new_ts < old_ts:
        return False
    try:
        return int(new_row.get("mention_count", 0)) >= int(old_row.get("mention_count", 0))
    except Exception:
        return False


def _infer_aliases_from_registry(
    *,
    term_registry_path: Path,
    logger: logging.Logger,
) -> dict[str, str]:
    if not term_registry_path.exists():
        return {}
    try:
        payload = json.loads(term_registry_path.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.warning("failed parsing term registry for alias inference", extra={"path": str(term_registry_path)})
        return {}
    if not isinstance(payload, list):
        return {}

    aliases: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        derived = _legacy_pattern_literal_to_definition(str(item.get("pattern", "")))
        if derived is None:
            continue
        if derived.name.casefold() != name.casefold():
            aliases.setdefault(name.casefold(), derived.name)
    return aliases


def _legacy_pattern_literal_to_definition(pattern: str) -> TermDefinition | None:
    raw = pattern.strip()
    if not raw.startswith("{") and not raw.startswith("["):
        return None
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        return None
    variants = _extract_custom_strike_variants(parsed)
    if not variants:
        return None
    name = _canonical_term_name(variants[0])
    normalized = [value for value in (_normalize_text(v) for v in variants) if value]
    deduped: list[str] = []
    seen: set[str] = set()
    for value in normalized:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    pattern_value, is_regex = _build_pattern_from_variants(deduped)
    return TermDefinition(name=name, pattern=pattern_value, is_regex=is_regex)


def _load_registry_term_names(path: Path, *, logger: logging.Logger) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.warning("failed reading term registry; treating as empty", extra={"path": str(path)})
        return set()
    if not isinstance(payload, list):
        logger.warning("invalid term registry format; treating as empty", extra={"path": str(path)})
        return set()
    names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if name:
            names.add(name.casefold())
    return names
