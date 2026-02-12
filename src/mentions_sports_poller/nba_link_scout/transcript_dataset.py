from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TranscriptDatasetError(RuntimeError):
    pass


@dataclass(frozen=True)
class TermDefinition:
    name: str
    pattern: str
    is_regex: bool = False


GAME_FACTORS_FIELDNAMES = (
    "audio_id",
    "feed_label",
    "transcript_file",
    "video_url",
    "source_feed_page",
    "game_id",
    "date",
    "away",
    "home",
    "matchup",
    "is_national_tv",
    "is_local_tv",
    "tv_scope_label",
    "commentators",
    "broadcast_networks",
    "broadcast_scopes",
    "players_away",
    "players_home",
    "players_all",
    "roster_away_json",
    "roster_home_json",
    "created_at_utc",
)

GAME_TERM_FIELDNAMES = (
    "audio_id",
    "feed_label",
    "game_id",
    "date",
    "away",
    "home",
    "term",
    "mention_count",
    "processed_at_utc",
)


def load_term_definitions(*, terms_file: str | Path | None = None, inline_terms: list[str] | None = None) -> list[TermDefinition]:
    terms: list[TermDefinition] = []
    if terms_file:
        terms.extend(_load_terms_from_file(Path(terms_file)))
    if inline_terms:
        for value in inline_terms:
            text = value.strip()
            if text:
                terms.append(TermDefinition(name=text, pattern=text, is_regex=False))
    if not terms:
        raise TranscriptDatasetError("no terms configured; pass --terms-file and/or --term")

    deduped: list[TermDefinition] = []
    seen: set[str] = set()
    for term in terms:
        key = term.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def build_transcript_feature_dataset(
    *,
    transcripts_dir: str | Path,
    manifest_file: str | Path,
    game_info_dir: str | Path,
    terms: list[TermDefinition],
    include_test_transcripts: bool = False,
    national_network_markers: tuple[str, ...] | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    term_counters = {term.name: _make_term_counter(term) for term in terms}
    manifest_by_audio_id = _load_manifest_map(Path(manifest_file))
    packet_lookup = _GamePacketLookup(game_info_dir=Path(game_info_dir), logger=log)

    transcript_paths = _list_transcript_files(
        transcripts_dir=Path(transcripts_dir),
        include_test_transcripts=include_test_transcripts,
    )
    rows_raw: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for transcript_path in transcript_paths:
        try:
            transcript_payload = _load_json_object(transcript_path)
            row = _build_audio_row(
                transcript_path=transcript_path,
                transcript_payload=transcript_payload,
                manifest_by_audio_id=manifest_by_audio_id,
                packet_lookup=packet_lookup,
                term_counters=term_counters,
                national_network_markers=national_network_markers or tuple(),
            )
            rows_raw.append(row)
        except Exception as exc:
            message = f"failed to process transcript {transcript_path}: {exc}"
            log.error(message)
            errors.append({"transcript_file": str(transcript_path), "error": str(exc)})

    rows_raw.sort(key=lambda row: (row.get("date", ""), row.get("away", ""), row.get("home", ""), row.get("feed_label", "")))
    commentator_vocab = sorted({name for row in rows_raw for name in row.get("commentators", [])})
    player_vocab = sorted({name for row in rows_raw for name in row.get("players_all", [])})

    audio_rows = [
        _materialize_audio_row(
            row=row,
            terms=terms,
            commentator_vocab=commentator_vocab,
            player_vocab=player_vocab,
        )
        for row in rows_raw
    ]
    game_rows = _build_game_rows(
        rows_raw=rows_raw,
        terms=terms,
        commentator_vocab=commentator_vocab,
        player_vocab=player_vocab,
    )
    summary = {
        "transcripts_seen": len(transcript_paths),
        "audio_rows": len(audio_rows),
        "game_rows": len(game_rows),
        "errors": len(errors),
    }
    return {
        "generated_at_utc": _utc_now_iso(),
        "terms": [{"name": term.name, "pattern": term.pattern, "is_regex": term.is_regex} for term in terms],
        "feature_catalog": {
            "term_columns": _build_term_columns(terms),
            "commentator_columns": _build_presence_columns(commentator_vocab, prefix="commentator__"),
            "player_columns": _build_presence_columns(player_vocab, prefix="player__"),
        },
        "audio_rows": audio_rows,
        "game_rows": game_rows,
        "errors": errors,
        "summary": summary,
    }


def write_dataset_outputs(
    *,
    dataset: dict[str, Any],
    output_json: str | Path,
    output_csv: str | Path | None = None,
) -> dict[str, str]:
    json_path = Path(output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(dataset, indent=2, sort_keys=True), encoding="utf-8")

    outputs = {"json": str(json_path)}
    if output_csv is not None:
        csv_path = Path(output_csv)
        rows = dataset.get("audio_rows", [])
        if not isinstance(rows, list):
            raise TranscriptDatasetError("dataset.audio_rows must be a list")
        _write_audio_rows_csv(csv_path, rows)
        outputs["csv"] = str(csv_path)
    return outputs


def default_output_json_path() -> Path:
    return Path("data") / "modeling" / "nba_transcript_term_dataset.json"


def default_output_csv_path() -> Path:
    return Path("data") / "modeling" / "nba_transcript_term_audio_rows.csv"


def default_game_factors_path() -> Path:
    return Path("data") / "modeling" / "nba_game_factors.csv"


def default_game_term_mentions_path() -> Path:
    return Path("data") / "modeling" / "nba_game_term_mentions.csv"


def default_term_registry_path() -> Path:
    return Path("data") / "modeling" / "nba_terms_registry.json"


def build_incremental_game_term_datasets(
    *,
    mode: str,
    transcripts_dir: str | Path,
    manifest_file: str | Path,
    game_info_dir: str | Path,
    include_test_transcripts: bool = False,
    national_network_markers: tuple[str, ...] | None = None,
    terms: list[TermDefinition] | None = None,
    game_factors_path: str | Path | None = None,
    game_term_mentions_path: str | Path | None = None,
    term_registry_path: str | Path | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    mode_normalized = mode.strip().lower()
    if mode_normalized not in {"game", "term", "both"}:
        raise TranscriptDatasetError("mode must be one of: game, term, both")

    game_path = Path(game_factors_path) if game_factors_path else default_game_factors_path()
    term_mentions_path = Path(game_term_mentions_path) if game_term_mentions_path else default_game_term_mentions_path()
    registry_path = Path(term_registry_path) if term_registry_path else default_term_registry_path()
    terms_input = terms or []

    existing_games = _load_existing_game_rows(game_path)
    existing_game_keys = {_game_row_key(row) for row in existing_games if _game_row_key(row) is not None}
    appended_game_rows: list[dict[str, Any]] = []
    game_factor_errors: list[dict[str, str]] = []

    if mode_normalized in {"game", "both"}:
        new_game_rows, game_factor_errors = _extract_game_factor_rows_from_transcripts(
            transcripts_dir=Path(transcripts_dir),
            manifest_file=Path(manifest_file),
            game_info_dir=Path(game_info_dir),
            include_test_transcripts=include_test_transcripts,
            national_network_markers=national_network_markers or tuple(),
            logger=log,
        )
        for row in new_game_rows:
            key = _game_row_key(row)
            if key is None or key in existing_game_keys:
                continue
            appended_game_rows.append(row)
            existing_game_keys.add(key)
            existing_games.append(row)
        _append_rows_to_csv(
            path=game_path,
            rows=appended_game_rows,
            fieldnames=GAME_FACTORS_FIELDNAMES,
        )

    registry_before = _load_term_registry(registry_path)
    registry_terms = _registry_to_terms(registry_before)
    added_registry_terms = _merge_terms_into_registry(
        registry=registry_before,
        incoming_terms=terms_input if mode_normalized in {"term", "both"} else [],
        logger=log,
    )
    if added_registry_terms > 0:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry_before, indent=2, sort_keys=True), encoding="utf-8")
    registry_terms = _registry_to_terms(registry_before)

    active_terms: list[TermDefinition] = []
    if mode_normalized == "term":
        if not terms_input:
            raise TranscriptDatasetError("term mode requires --term and/or --terms-file")
        active_terms = terms_input
    elif mode_normalized == "game":
        active_terms = registry_terms
    else:
        # both
        by_name: dict[str, TermDefinition] = {}
        for term in registry_terms + terms_input:
            key = term.name.casefold()
            by_name[key] = term
        active_terms = list(by_name.values())

    existing_term_rows = _load_existing_term_rows(term_mentions_path)
    existing_term_keys = {_term_row_key(row) for row in existing_term_rows if _term_row_key(row) is not None}
    appended_term_rows: list[dict[str, Any]] = []
    transcript_errors: list[dict[str, str]] = []

    if active_terms:
        if not existing_games:
            log.warning("no game rows available; term dataset update skipped")
        else:
            transcript_entries, transcript_errors = _build_game_transcript_entries(
                transcripts_dir=Path(transcripts_dir),
                manifest_file=Path(manifest_file),
                game_info_dir=Path(game_info_dir),
                include_test_transcripts=include_test_transcripts,
                national_network_markers=national_network_markers or tuple(),
                logger=log,
            )
            text_by_key: dict[tuple[str, str], str] = {}
            for entry in transcript_entries:
                entry_key = _game_row_key(entry)
                if entry_key is None:
                    continue
                text_by_key[entry_key] = str(entry.get("text", ""))
            counters = {term.name: _make_term_counter(term) for term in active_terms}
            for game_row in sorted(existing_games, key=lambda row: (row.get("date", ""), row.get("away", ""), row.get("home", ""))):
                game_key = _game_row_key(game_row)
                if game_key is None:
                    continue
                game_id = str(game_row.get("game_id", "")).strip()
                if not game_id:
                    continue
                text = text_by_key.get(game_key, "")
                audio_id = str(game_row.get("audio_id", "")).strip()
                feed_label = str(game_row.get("feed_label", "")).strip()
                for term in active_terms:
                    key = (
                        game_id,
                        _coalesce_text(audio_id, feed_label).casefold(),
                        term.name.casefold(),
                    )
                    if key in existing_term_keys:
                        continue
                    mention_count = len(list(counters[term.name].finditer(text)))
                    appended_term_rows.append(
                        {
                            "audio_id": audio_id,
                            "feed_label": feed_label,
                            "game_id": game_id,
                            "date": str(game_row.get("date", "")),
                            "away": str(game_row.get("away", "")),
                            "home": str(game_row.get("home", "")),
                            "term": term.name,
                            "mention_count": mention_count,
                            "processed_at_utc": _utc_now_iso(),
                        }
                    )
                    existing_term_keys.add(key)
            _append_rows_to_csv(
                path=term_mentions_path,
                rows=appended_term_rows,
                fieldnames=GAME_TERM_FIELDNAMES,
            )

    return {
        "mode": mode_normalized,
        "outputs": {
            "game_factors_csv": str(game_path),
            "game_term_mentions_csv": str(term_mentions_path),
            "term_registry_json": str(registry_path),
        },
        "summary": {
            "existing_game_rows": len(existing_games) - len(appended_game_rows),
            "appended_game_rows": len(appended_game_rows),
            "existing_term_rows": len(existing_term_rows),
            "appended_term_rows": len(appended_term_rows),
            "registered_terms_total": len(registry_before),
            "registered_terms_added": added_registry_terms,
            "active_terms_count": len(active_terms),
        },
        "errors": {
            "game_factor_errors": game_factor_errors,
            "transcript_errors": transcript_errors,
        },
    }


def _load_terms_from_file(path: Path) -> list[TermDefinition]:
    if not path.exists():
        raise TranscriptDatasetError(f"terms file not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            raise TranscriptDatasetError(f"terms JSON must be a list: {path}")
        terms: list[TermDefinition] = []
        for idx, item in enumerate(payload):
            if isinstance(item, str):
                text = item.strip()
                if text:
                    terms.append(TermDefinition(name=text, pattern=text, is_regex=False))
                continue
            if not isinstance(item, dict):
                raise TranscriptDatasetError(f"invalid term item at index {idx} in {path}")
            name = str(item.get("name", "")).strip()
            pattern = str(item.get("pattern", "")).strip()
            is_regex = bool(item.get("regex", False))
            if not name:
                raise TranscriptDatasetError(f"missing term name at index {idx} in {path}")
            if not pattern:
                pattern = name
            terms.append(TermDefinition(name=name, pattern=pattern, is_regex=is_regex))
        return terms

    terms = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        terms.append(TermDefinition(name=stripped, pattern=stripped, is_regex=False))
    return terms


def _make_term_counter(term: TermDefinition) -> re.Pattern[str]:
    if term.is_regex:
        try:
            return re.compile(term.pattern, re.IGNORECASE)
        except re.error as exc:
            raise TranscriptDatasetError(f"invalid regex for term '{term.name}': {exc}") from exc
    escaped = re.escape(term.pattern.strip())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _load_existing_game_rows(path: Path) -> list[dict[str, Any]]:
    return _load_csv_rows(path)


def _load_existing_term_rows(path: Path) -> list[dict[str, Any]]:
    return _load_csv_rows(path)


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _append_rows_to_csv(*, path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _load_term_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise TranscriptDatasetError(f"term registry must be a list: {path}")
    out: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        pattern = str(item.get("pattern", "")).strip() or name
        if not name:
            continue
        out.append({"name": name, "pattern": pattern, "is_regex": bool(item.get("is_regex", False))})
    return out


def _registry_to_terms(rows: list[dict[str, Any]]) -> list[TermDefinition]:
    terms: list[TermDefinition] = []
    for row in rows:
        terms.append(
            TermDefinition(
                name=str(row.get("name", "")),
                pattern=str(row.get("pattern", "")) or str(row.get("name", "")),
                is_regex=bool(row.get("is_regex", False)),
            )
        )
    return terms


def _merge_terms_into_registry(*, registry: list[dict[str, Any]], incoming_terms: list[TermDefinition], logger: logging.Logger) -> int:
    if not incoming_terms:
        return 0
    by_key: dict[str, dict[str, Any]] = {}
    for row in registry:
        name = str(row.get("name", "")).strip()
        if name:
            by_key[name.casefold()] = row

    added = 0
    for term in incoming_terms:
        key = term.name.casefold()
        existing = by_key.get(key)
        if existing is None:
            record = {
                "name": term.name,
                "pattern": term.pattern,
                "is_regex": term.is_regex,
                "added_at_utc": _utc_now_iso(),
            }
            registry.append(record)
            by_key[key] = record
            added += 1
            continue
        existing_pattern = str(existing.get("pattern", ""))
        existing_is_regex = bool(existing.get("is_regex", False))
        if existing_pattern != term.pattern or existing_is_regex != term.is_regex:
            logger.warning(
                "term '%s' already exists in registry with different pattern/regex; keeping existing definition",
                term.name,
            )
    registry.sort(key=lambda item: str(item.get("name", "")).casefold())
    return added


def _extract_game_factor_rows_from_transcripts(
    *,
    transcripts_dir: Path,
    manifest_file: Path,
    game_info_dir: Path,
    include_test_transcripts: bool,
    national_network_markers: tuple[str, ...],
    logger: logging.Logger,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    entries, errors = _build_game_transcript_entries(
        transcripts_dir=transcripts_dir,
        manifest_file=manifest_file,
        game_info_dir=game_info_dir,
        include_test_transcripts=include_test_transcripts,
        national_network_markers=national_network_markers,
        logger=logger,
    )
    rows: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        row.pop("text", None)
        rows.append(row)
    rows.sort(key=lambda row: (row.get("date", ""), row.get("away", ""), row.get("home", ""), row.get("feed_label", "")))
    return rows, errors


def _extract_packets(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("packets"), list):
        return [item for item in payload["packets"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _packet_to_game_factor_row(
    *,
    packet: dict[str, Any],
    audio_id: str,
    feed_label: str,
    transcript_file: str,
    video_url: str,
    source_feed_page: str,
    national_network_markers: tuple[str, ...],
) -> dict[str, Any] | None:
    game_id = _coalesce_text(packet.get("game_id"))
    if not game_id:
        return None
    away = _coalesce_text(packet.get("away"))
    home = _coalesce_text(packet.get("home"))
    date_value = _coalesce_text(packet.get("date"))

    commentators = _extract_commentator_names(packet)
    players_away, players_home = _extract_players(packet)
    players_all = sorted(set(players_away + players_home))
    broadcast_networks, broadcast_scopes = _extract_broadcast_metadata(packet)
    is_national_tv = _is_national_tv(
        packet=packet,
        scopes=broadcast_scopes,
        networks=broadcast_networks,
        national_network_markers=national_network_markers,
    )
    tv_scope_label = _classify_tv_scope(scopes=broadcast_scopes, is_national_tv=is_national_tv)
    rosters = packet.get("rosters", {})
    roster_away_json = "[]"
    roster_home_json = "[]"
    if isinstance(rosters, dict):
        away_payload = rosters.get("away", [])
        home_payload = rosters.get("home", [])
        roster_away_json = json.dumps(away_payload if isinstance(away_payload, list) else [], ensure_ascii=False, sort_keys=True)
        roster_home_json = json.dumps(home_payload if isinstance(home_payload, list) else [], ensure_ascii=False, sort_keys=True)

    return {
        "audio_id": audio_id,
        "feed_label": feed_label,
        "transcript_file": transcript_file,
        "video_url": video_url,
        "source_feed_page": source_feed_page,
        "game_id": game_id,
        "date": date_value,
        "away": away,
        "home": home,
        "matchup": _matchup(away, home),
        "is_national_tv": bool(is_national_tv),
        "is_local_tv": tv_scope_label == "local",
        "tv_scope_label": tv_scope_label,
        "commentators": "|".join(commentators),
        "broadcast_networks": "|".join(broadcast_networks),
        "broadcast_scopes": "|".join(broadcast_scopes),
        "players_away": "|".join(players_away),
        "players_home": "|".join(players_home),
        "players_all": "|".join(players_all),
        "roster_away_json": roster_away_json,
        "roster_home_json": roster_home_json,
        "created_at_utc": _utc_now_iso(),
    }


def _build_game_transcript_entries(
    *,
    transcripts_dir: Path,
    manifest_file: Path,
    game_info_dir: Path,
    include_test_transcripts: bool,
    national_network_markers: tuple[str, ...],
    logger: logging.Logger,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    manifest_by_audio_id = _load_manifest_map(manifest_file)
    packet_lookup = _GamePacketLookup(game_info_dir=game_info_dir, logger=logger)
    transcript_paths = _list_transcript_files(
        transcripts_dir=transcripts_dir,
        include_test_transcripts=include_test_transcripts,
    )
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for transcript_path in transcript_paths:
        try:
            payload = _load_json_object(transcript_path)
            audio_id = _coalesce_text(payload.get("audio_id"), transcript_path.stem.split(".")[0])
            manifest_row = manifest_by_audio_id.get(audio_id, {})
            date_value = _coalesce_text(payload.get("date"), manifest_row.get("date"))
            away_value = _coalesce_text(payload.get("away"), manifest_row.get("away"))
            home_value = _coalesce_text(payload.get("home"), manifest_row.get("home"))
            feed_label = _coalesce_text(payload.get("feed_label"), manifest_row.get("feed_label"))
            video_url = _coalesce_text(payload.get("video_url"), manifest_row.get("video_url"))
            source_feed_page = _coalesce_text(payload.get("source_feed_page"), manifest_row.get("source_feed_page"))
            packet = packet_lookup.lookup(date_value=date_value, away_value=away_value, home_value=home_value)
            if not isinstance(packet, dict):
                continue
            row = _packet_to_game_factor_row(
                packet=packet,
                audio_id=audio_id,
                feed_label=feed_label,
                transcript_file=str(transcript_path),
                video_url=video_url,
                source_feed_page=source_feed_page,
                national_network_markers=national_network_markers,
            )
            if row is None:
                continue
            text = _pick_transcript_text(payload)
            row["text"] = text
            entries.append(row)
        except Exception as exc:
            logger.error("failed to process transcript for term aggregation %s: %s", transcript_path, exc)
            errors.append({"transcript_file": str(transcript_path), "error": str(exc)})
    return entries, errors


def _load_manifest_map(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise TranscriptDatasetError(f"manifest file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise TranscriptDatasetError(f"manifest must be a JSON list: {path}")
    out: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        audio_id = str(item.get("audio_id", "")).strip()
        if not audio_id:
            continue
        out[audio_id] = item
    return out


def _list_transcript_files(*, transcripts_dir: Path, include_test_transcripts: bool) -> list[Path]:
    if not transcripts_dir.exists():
        raise TranscriptDatasetError(f"transcripts dir not found: {transcripts_dir}")
    paths = sorted(path for path in transcripts_dir.glob("*.json") if path.is_file())
    if include_test_transcripts:
        return paths
    return [path for path in paths if ".test" not in path.name]


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TranscriptDatasetError(f"transcript must be a JSON object: {path}")
    return payload


def _build_audio_row(
    *,
    transcript_path: Path,
    transcript_payload: dict[str, Any],
    manifest_by_audio_id: dict[str, dict[str, Any]],
    packet_lookup: "_GamePacketLookup",
    term_counters: dict[str, re.Pattern[str]],
    national_network_markers: tuple[str, ...],
) -> dict[str, Any]:
    audio_id = str(transcript_payload.get("audio_id", "")).strip()
    if not audio_id:
        audio_id = transcript_path.stem.split(".")[0]
    if not audio_id:
        raise TranscriptDatasetError(f"unable to resolve audio_id from transcript file: {transcript_path}")

    manifest_row = manifest_by_audio_id.get(audio_id, {})
    date_value = _coalesce_text(transcript_payload.get("date"), manifest_row.get("date"))
    away_value = _coalesce_text(transcript_payload.get("away"), manifest_row.get("away"))
    home_value = _coalesce_text(transcript_payload.get("home"), manifest_row.get("home"))
    feed_label = _coalesce_text(transcript_payload.get("feed_label"), manifest_row.get("feed_label"))
    video_url = _coalesce_text(transcript_payload.get("video_url"), manifest_row.get("video_url"))

    text = _pick_transcript_text(transcript_payload)
    term_counts: dict[str, int] = {}
    for term_name, pattern in term_counters.items():
        term_counts[term_name] = len(list(pattern.finditer(text)))
    total_term_hits = int(sum(term_counts.values()))

    packet = packet_lookup.lookup(date_value=date_value, away_value=away_value, home_value=home_value)
    commentators = _extract_commentator_names(packet)
    players_away, players_home = _extract_players(packet)
    players_all = sorted(set(players_away + players_home))
    broadcast_networks, broadcast_scopes = _extract_broadcast_metadata(packet)
    is_national_tv = _is_national_tv(
        packet=packet,
        scopes=broadcast_scopes,
        networks=broadcast_networks,
        national_network_markers=national_network_markers,
    )
    tv_scope_label = _classify_tv_scope(
        scopes=broadcast_scopes,
        is_national_tv=is_national_tv,
    )
    return {
        "audio_id": audio_id,
        "date": date_value,
        "away": away_value,
        "home": home_value,
        "matchup": _matchup(away_value, home_value),
        "feed_label": feed_label,
        "video_url": video_url,
        "source_feed_page": _coalesce_text(transcript_payload.get("source_feed_page"), manifest_row.get("source_feed_page")),
        "transcript_file": str(transcript_path),
        "transcript_word_count": len(re.findall(r"\b[\w'-]+\b", text)),
        "transcript_char_count": len(text),
        "term_counts": term_counts,
        "total_term_hits": total_term_hits,
        "is_national_tv": is_national_tv,
        "is_local_tv": tv_scope_label == "local",
        "tv_scope_label": tv_scope_label,
        "broadcast_networks": broadcast_networks,
        "broadcast_scopes": broadcast_scopes,
        "commentators": commentators,
        "players_away": players_away,
        "players_home": players_home,
        "players_all": players_all,
    }


def _pick_transcript_text(payload: dict[str, Any]) -> str:
    corrected = payload.get("transcript_text")
    if isinstance(corrected, str) and corrected.strip():
        return corrected
    raw = payload.get("transcript_text_raw")
    if isinstance(raw, str) and raw.strip():
        return raw
    chunks = payload.get("chunks", [])
    if isinstance(chunks, list):
        parts: list[str] = []
        for item in chunks:
            if not isinstance(item, dict):
                continue
            text = item.get("transcript_text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
        if parts:
            return "\n".join(parts)
    return ""


def _coalesce_text(*values: Any) -> str:
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def _extract_commentator_names(packet: dict[str, Any] | None) -> list[str]:
    if not isinstance(packet, dict):
        return []
    commentary = packet.get("commentary")
    if not isinstance(commentary, dict):
        return []
    raw = commentary.get("commentators")
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict):
            name = _coalesce_text(item.get("name"))
        else:
            name = _coalesce_text(item)
        if name and name not in out:
            out.append(name)
    return out


def _extract_players(packet: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not isinstance(packet, dict):
        return ([], [])
    rosters = packet.get("rosters")
    if not isinstance(rosters, dict):
        return ([], [])

    def names_for(side: str) -> list[str]:
        players = rosters.get(side, [])
        out: list[str] = []
        if not isinstance(players, list):
            return out
        for item in players:
            if not isinstance(item, dict):
                continue
            name = _coalesce_text(item.get("name"))
            if name and name not in out:
                out.append(name)
        return out

    away = names_for("away")
    home = names_for("home")
    return (away, home)


def _extract_broadcast_metadata(packet: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not isinstance(packet, dict):
        return ([], [])
    commentary = packet.get("commentary")
    if not isinstance(commentary, dict):
        return ([], [])
    teams = commentary.get("broadcast_teams")
    if not isinstance(teams, list):
        return ([], [])
    networks: list[str] = []
    scopes: list[str] = []
    for item in teams:
        if not isinstance(item, dict):
            continue
        network = _coalesce_text(item.get("network"))
        scope = _coalesce_text(item.get("scope"))
        if network and network not in networks:
            networks.append(network)
        if scope and scope not in scopes:
            scopes.append(scope)
    return (networks, scopes)


def _is_national_tv(
    *,
    packet: dict[str, Any] | None,
    scopes: list[str],
    networks: list[str],
    national_network_markers: tuple[str, ...],
) -> bool:
    markers = tuple(marker.casefold() for marker in national_network_markers if marker.strip())
    for scope in scopes:
        lowered = scope.casefold()
        if "national" in lowered:
            return True
    if markers:
        for network in networks:
            lowered = network.casefold()
            if any(marker in lowered for marker in markers):
                return True

    if not isinstance(packet, dict):
        return False
    commentary = packet.get("commentary")
    if not isinstance(commentary, dict):
        return False
    teams = commentary.get("broadcast_teams")
    if not isinstance(teams, list):
        return False
    for item in teams:
        if not isinstance(item, dict):
            continue
        broadcast_type = _coalesce_text(item.get("broadcast_type"))
        scope = _coalesce_text(item.get("scope"))
        if "tv" in broadcast_type.casefold() and "national" in scope.casefold():
            return True
    return False


def _classify_tv_scope(*, scopes: list[str], is_national_tv: bool) -> str:
    if is_national_tv:
        return "national"
    lowered = [scope.casefold() for scope in scopes]
    if any("local" in scope or "regional" in scope for scope in lowered):
        return "local"
    if lowered:
        return "local"
    return "unknown"


def _materialize_audio_row(
    *,
    row: dict[str, Any],
    terms: list[TermDefinition],
    commentator_vocab: list[str],
    player_vocab: list[str],
) -> dict[str, Any]:
    out = {
        "audio_id": row.get("audio_id", ""),
        "date": row.get("date", ""),
        "away": row.get("away", ""),
        "home": row.get("home", ""),
        "matchup": row.get("matchup", ""),
        "feed_label": row.get("feed_label", ""),
        "video_url": row.get("video_url", ""),
        "source_feed_page": row.get("source_feed_page", ""),
        "transcript_file": row.get("transcript_file", ""),
        "transcript_word_count": int(row.get("transcript_word_count", 0)),
        "transcript_char_count": int(row.get("transcript_char_count", 0)),
        "total_term_hits": int(row.get("total_term_hits", 0)),
        "is_national_tv": bool(row.get("is_national_tv", False)),
        "is_local_tv": bool(row.get("is_local_tv", False)),
        "tv_scope_label": row.get("tv_scope_label", "unknown"),
        "broadcast_networks": "|".join(row.get("broadcast_networks", [])),
        "broadcast_scopes": "|".join(row.get("broadcast_scopes", [])),
        "commentators": "|".join(row.get("commentators", [])),
        "players_away": "|".join(row.get("players_away", [])),
        "players_home": "|".join(row.get("players_home", [])),
        "players_all": "|".join(row.get("players_all", [])),
    }

    term_counts = row.get("term_counts", {})
    for term in terms:
        column = _term_column_name(term.name)
        out[column] = int(term_counts.get(term.name, 0))

    commentators = set(row.get("commentators", []))
    for name in commentator_vocab:
        out[_presence_column_name("commentator__", name)] = 1 if name in commentators else 0

    players = set(row.get("players_all", []))
    for name in player_vocab:
        out[_presence_column_name("player__", name)] = 1 if name in players else 0
    return out


def _build_game_rows(
    *,
    rows_raw: list[dict[str, Any]],
    terms: list[TermDefinition],
    commentator_vocab: list[str],
    player_vocab: list[str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows_raw:
        key = (str(row.get("date", "")), str(row.get("away", "")), str(row.get("home", "")))
        grouped.setdefault(key, []).append(row)

    out: list[dict[str, Any]] = []
    for key in sorted(grouped.keys()):
        date_value, away_value, home_value = key
        rows = grouped[key]
        all_commentators = sorted({name for row in rows for name in row.get("commentators", [])})
        all_players = sorted({name for row in rows for name in row.get("players_all", [])})
        game_row: dict[str, Any] = {
            "date": date_value,
            "away": away_value,
            "home": home_value,
            "matchup": _matchup(away_value, home_value),
            "audio_ids": "|".join(str(row.get("audio_id", "")) for row in rows),
            "feed_labels": "|".join(str(row.get("feed_label", "")) for row in rows),
            "feed_count": len(rows),
            "any_national_tv": any(bool(row.get("is_national_tv", False)) for row in rows),
            "national_feed_count": sum(1 for row in rows if bool(row.get("is_national_tv", False))),
            "any_local_tv": any(bool(row.get("is_local_tv", False)) for row in rows),
            "local_feed_count": sum(1 for row in rows if bool(row.get("is_local_tv", False))),
            "tv_scope_labels": "|".join(sorted({str(row.get("tv_scope_label", "unknown")) for row in rows})),
            "commentators": "|".join(all_commentators),
            "players_all": "|".join(all_players),
            "total_term_hits": sum(int(row.get("total_term_hits", 0)) for row in rows),
        }

        for term in terms:
            term_total = sum(int(row.get("term_counts", {}).get(term.name, 0)) for row in rows)
            game_row[_term_column_name(term.name)] = term_total

        commentator_set = set(all_commentators)
        for name in commentator_vocab:
            game_row[_presence_column_name("commentator__", name)] = 1 if name in commentator_set else 0

        player_set = set(all_players)
        for name in player_vocab:
            game_row[_presence_column_name("player__", name)] = 1 if name in player_set else 0

        out.append(game_row)
    return out


def _write_audio_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_term_columns(terms: list[TermDefinition]) -> list[dict[str, str]]:
    return [{"name": term.name, "column": _term_column_name(term.name)} for term in terms]


def _build_presence_columns(values: list[str], *, prefix: str) -> list[dict[str, str]]:
    return [{"name": value, "column": _presence_column_name(prefix, value)} for value in values]


def _term_column_name(term_name: str) -> str:
    return f"term_count__{_slug(term_name)}"


def _presence_column_name(prefix: str, value: str) -> str:
    return f"{prefix}{_slug(value)}"


def _game_row_key(row: dict[str, Any]) -> tuple[str, str] | None:
    game_id = str(row.get("game_id", "")).strip()
    if not game_id:
        return None
    audio_or_feed = _coalesce_text(row.get("audio_id"), row.get("feed_label"))
    return (game_id, audio_or_feed.casefold())


def _term_row_key(row: dict[str, Any]) -> tuple[str, str, str] | None:
    game_id = str(row.get("game_id", "")).strip()
    term = str(row.get("term", "")).strip()
    if not game_id or not term:
        return None
    audio_or_feed = _coalesce_text(row.get("audio_id"), row.get("feed_label"))
    return (game_id, audio_or_feed.casefold(), term.casefold())


def _slug(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "_" for char in value.strip()]
    slug = "".join(chars)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "x"


def _matchup(away: str, home: str) -> str:
    away_text = away.strip()
    home_text = home.strip()
    if away_text and home_text:
        return f"{away_text} @ {home_text}"
    return away_text or home_text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _GamePacketLookup:
    def __init__(self, *, game_info_dir: Path, logger: logging.Logger) -> None:
        self._game_info_dir = game_info_dir
        self._logger = logger
        self._packets_by_date: dict[str, list[dict[str, Any]]] = {}

    def lookup(self, *, date_value: str, away_value: str, home_value: str) -> dict[str, Any] | None:
        if not date_value:
            return None
        packets = self._load_packets_for_date(date_value)
        target_away = away_value.strip().casefold()
        target_home = home_value.strip().casefold()
        for packet in packets:
            if str(packet.get("away", "")).strip().casefold() != target_away:
                continue
            if str(packet.get("home", "")).strip().casefold() != target_home:
                continue
            return packet
        return None

    def _load_packets_for_date(self, date_value: str) -> list[dict[str, Any]]:
        if date_value in self._packets_by_date:
            return self._packets_by_date[date_value]
        path = self._game_info_dir / f"nba_game_info_{date_value}.json"
        if not path.exists():
            self._logger.warning("game info file missing for date %s: %s", date_value, path)
            self._packets_by_date[date_value] = []
            return []
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        packets: list[dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("packets"), list):
            packets = [item for item in payload["packets"] if isinstance(item, dict)]
        elif isinstance(payload, list):
            packets = [item for item in payload if isinstance(item, dict)]
        else:
            self._logger.warning("unsupported game info payload format in %s", path)
            packets = []
        self._packets_by_date[date_value] = packets
        return packets
