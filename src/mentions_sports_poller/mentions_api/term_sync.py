from __future__ import annotations

import json
import logging
import re
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

    kalshi_terms = extract_kalshi_term_definitions(markets)
    if not kalshi_terms:
        return {"enabled": True, "kalshi_terms_seen": 0, "new_terms": 0}

    registry_names = _load_registry_term_names(Path(term_registry_path), logger=log)
    new_terms = [
        term for term in kalshi_terms if term.name.casefold() not in registry_names
    ]
    if not new_terms:
        return {
            "enabled": True,
            "kalshi_terms_seen": len(kalshi_terms),
            "new_terms": 0,
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
    }


def extract_kalshi_term_definitions(
    markets: list[DiscoveredMarket],
) -> list[TermDefinition]:
    by_name: dict[str, TermDefinition] = {}
    for market in markets:
        variants = _extract_human_variants(market)
        if variants:
            term_name = _canonical_term_name(variants[0])
            pattern, is_regex = _build_pattern_from_variants(variants)
        else:
            term_name = _term_name_from_ticker(market.ticker)
            if not term_name:
                continue
            pattern = term_name
            is_regex = False
        key = term_name.casefold()
        by_name.setdefault(
            key,
            TermDefinition(name=term_name, pattern=pattern, is_regex=is_regex),
        )
    return [by_name[key] for key in sorted(by_name.keys())]


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
