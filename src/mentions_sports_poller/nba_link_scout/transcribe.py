from __future__ import annotations

from contextlib import ExitStack
import difflib
import json
import mimetypes
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

ProgressCallback = Callable[[dict[str, Any]], None]
ClipperFn = Callable[[Path, Path, float, str], None]
DurationProberFn = Callable[[Path, str], float]

NBA_TEAM_NICKNAMES: dict[str, str] = {
    "atlanta hawks": "Hawks",
    "boston celtics": "Celtics",
    "brooklyn nets": "Nets",
    "charlotte hornets": "Hornets",
    "chicago bulls": "Bulls",
    "cleveland cavaliers": "Cavaliers",
    "dallas mavericks": "Mavericks",
    "denver nuggets": "Nuggets",
    "detroit pistons": "Pistons",
    "golden state warriors": "Warriors",
    "houston rockets": "Rockets",
    "indiana pacers": "Pacers",
    "los angeles clippers": "Clippers",
    "los angeles lakers": "Lakers",
    "memphis grizzlies": "Grizzlies",
    "miami heat": "Heat",
    "milwaukee bucks": "Bucks",
    "minnesota timberwolves": "Timberwolves",
    "new orleans pelicans": "Pelicans",
    "new york knicks": "Knicks",
    "oklahoma city thunder": "Thunder",
    "orlando magic": "Magic",
    "philadelphia 76ers": "76ers",
    "phoenix suns": "Suns",
    "portland trail blazers": "Trail Blazers",
    "sacramento kings": "Kings",
    "san antonio spurs": "Spurs",
    "toronto raptors": "Raptors",
    "utah jazz": "Jazz",
    "washington wizards": "Wizards",
}


class TranscriptionError(RuntimeError):
    pass


def transcribe_audio_from_manifest(
    *,
    manifest_file: str | Path,
    audio_id: str,
    game_info_file: str | Path,
    glossary_file: str | Path,
    model: str = "gpt-4o-transcribe",
    api_key_env: str = "OPENAI_API_KEY",
    timeout_seconds: float = 900.0,
    output_path: str | Path | None = None,
    dry_run: bool = False,
    max_seconds: float | None = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
    chunk_seconds: float = 900.0,
    chunk_overlap_seconds: float = 0.0,
    progress_callback: ProgressCallback | None = None,
    clipper: ClipperFn | None = None,
    duration_prober: DurationProberFn | None = None,
    session: requests.Session | Any | None = None,
) -> dict[str, Any]:
    _emit_progress(progress_callback, percent=0, stage="start")
    audio_row = _load_audio_row(manifest_file=Path(manifest_file), audio_id=audio_id)
    audio_path = Path(str(audio_row.get("audio_path", "")))
    if not audio_path.exists():
        raise TranscriptionError(f"audio file not found for {audio_id}: {audio_path}")
    _emit_progress(progress_callback, percent=10, stage="audio_row_loaded")

    game_packet = _load_matching_game_packet(game_info_file=Path(game_info_file), audio_row=audio_row)
    glossary_text = Path(glossary_file).read_text(encoding="utf-8-sig")
    _emit_progress(progress_callback, percent=20, stage="context_loaded")
    prompt = _build_transcription_prompt(
        audio_row=audio_row,
        game_packet=game_packet,
        glossary_text=glossary_text,
    )

    if output_path is None:
        output_path = _default_transcript_output_path(audio_id=audio_id, max_seconds=max_seconds)
    output_path = Path(output_path)
    normalized_max_seconds = _normalize_positive_float(max_seconds, field_name="max_seconds")
    normalized_chunk_seconds = _normalize_chunk_seconds(chunk_seconds)
    normalized_overlap = _normalize_overlap(
        chunk_overlap_seconds=chunk_overlap_seconds,
        chunk_seconds=normalized_chunk_seconds,
    )

    if dry_run:
        result = {
            "audio_id": audio_id,
            "audio_path": str(audio_path),
            "transcribed_audio_path": str(audio_path),
            "output_path": str(output_path),
            "model": model,
            "prompt_chars": len(prompt),
            "planned_only": True,
            "max_seconds": normalized_max_seconds,
            "ffmpeg_bin": ffmpeg_bin,
            "ffprobe_bin": ffprobe_bin,
            "chunk_seconds": normalized_chunk_seconds,
            "chunk_overlap_seconds": normalized_overlap,
            "game_packet_match": {
                "date": game_packet.get("date", ""),
                "away": game_packet.get("away", ""),
                "home": game_packet.get("home", ""),
            },
        }
        _write_json(output_path, result)
        _emit_progress(progress_callback, percent=100, stage="dry_run_complete")
        return result

    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        raise TranscriptionError(f"{api_key_env} is not set")

    active_session = session or requests.Session()
    owns_session = session is None
    active_clipper = clipper or _create_audio_clip_ffmpeg
    active_duration_prober = duration_prober or _probe_duration_seconds
    audio_for_transcription = audio_path
    temp_files: list[Path] = []
    chunk_results: list[dict[str, Any]] = []
    try:
        with ExitStack() as stack:
            if normalized_max_seconds is not None:
                _emit_progress(
                    progress_callback,
                    percent=30,
                    stage="clipping_start",
                    detail=f"first {normalized_max_seconds:g}s",
                )
                clip_path = _make_repo_temp_clip_path(
                    output_path=output_path,
                    source_path=audio_path,
                    max_seconds=normalized_max_seconds,
                )
                active_clipper(audio_path, clip_path, normalized_max_seconds, ffmpeg_bin)
                audio_for_transcription = clip_path
                temp_files.append(clip_path)
                stack.callback(_safe_unlink, clip_path)
                stack.callback(_safe_rmdir, clip_path.parent)
                _emit_progress(progress_callback, percent=40, stage="clipping_done")
            else:
                _emit_progress(progress_callback, percent=40, stage="audio_ready")

            chunk_specs = _build_chunk_specs(
                audio_path=audio_for_transcription,
                chunk_seconds=normalized_chunk_seconds,
                chunk_overlap_seconds=normalized_overlap,
                ffprobe_bin=ffprobe_bin,
                duration_prober=active_duration_prober,
            )
            total_chunks = len(chunk_specs)
            if total_chunks > 1:
                _emit_progress(
                    progress_callback,
                    percent=50,
                    stage="chunking_enabled",
                    detail=f"{total_chunks} chunks",
                )
            else:
                _emit_progress(progress_callback, percent=50, stage="single_chunk")

            for index, spec in enumerate(chunk_specs, start=1):
                chunk_path = audio_for_transcription
                if spec["start_seconds"] is not None and spec["end_seconds"] is not None:
                    chunk_path = _make_repo_temp_chunk_path(
                        output_path=output_path,
                        source_path=audio_for_transcription,
                        index=index,
                    )
                    duration = float(spec["end_seconds"]) - float(spec["start_seconds"])
                    active_clipper(audio_for_transcription, chunk_path, duration, ffmpeg_bin)
                    temp_files.append(chunk_path)
                    stack.callback(_safe_unlink, chunk_path)
                    stack.callback(_safe_rmdir, chunk_path.parent)

                chunk_percent = _chunk_progress_percent(index=index, total_chunks=total_chunks)
                _emit_progress(
                    progress_callback,
                    percent=chunk_percent,
                    stage="api_request_started",
                    detail=f"chunk {index}/{total_chunks}",
                )

                chunk_prompt = _build_chunk_prompt(prompt=prompt, index=index, total=total_chunks, spec=spec)
                api_response = _call_openai_transcription(
                    session=active_session,
                    api_key=api_key,
                    model=model,
                    audio_path=chunk_path,
                    prompt=chunk_prompt,
                    timeout_seconds=timeout_seconds,
                )
                chunk_text = _extract_transcript_text(api_response)
                chunk_results.append(
                    {
                        "index": index,
                        "start_seconds": spec["start_seconds"],
                        "end_seconds": spec["end_seconds"],
                        "audio_path": str(chunk_path),
                        "transcript_text": chunk_text,
                        "api_response": api_response,
                    }
                )

            _emit_progress(progress_callback, percent=94, stage="chunks_complete")
    finally:
        if owns_session:
            active_session.close()

    raw_transcript_text = _merge_chunk_texts([item["transcript_text"] for item in chunk_results])
    entities = _build_correction_entities(audio_row=audio_row, game_packet=game_packet)
    corrected_text, replacements = _apply_deterministic_entity_corrections(
        text=raw_transcript_text,
        entities=entities,
    )
    _emit_progress(progress_callback, percent=97, stage="entity_correction_complete")

    result = {
        "audio_id": audio_id,
        "date": str(audio_row.get("date", "")),
        "away": str(audio_row.get("away", "")),
        "home": str(audio_row.get("home", "")),
        "feed_label": str(audio_row.get("feed_label", "")),
        "video_url": str(audio_row.get("video_url", "")),
        "audio_path": str(audio_path),
        "transcribed_audio_path": str(audio_for_transcription),
        "max_seconds": normalized_max_seconds,
        "model": model,
        "prompt_chars": len(prompt),
        "chunk_seconds": normalized_chunk_seconds,
        "chunk_overlap_seconds": normalized_overlap,
        "chunks": chunk_results,
        "context_sources": {
            "game_info_file": str(Path(game_info_file)),
            "glossary_file": str(Path(glossary_file)),
        },
        "transcript_text_raw": raw_transcript_text,
        "transcript_text": corrected_text,
        "entity_corrections": replacements,
        "correction_entities": entities,
        "generated_at_utc": _utc_now_iso(),
    }
    _write_json(output_path, result)
    result["output_path"] = str(output_path)
    _emit_progress(progress_callback, percent=100, stage="complete")
    return result


def _load_audio_row(*, manifest_file: Path, audio_id: str) -> dict[str, Any]:
    rows = _load_json_list(manifest_file)
    for row in rows:
        if str(row.get("audio_id", "")) == audio_id:
            return row
    raise TranscriptionError(f"audio_id not found in manifest: {audio_id}")


def _load_matching_game_packet(*, game_info_file: Path, audio_row: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(game_info_file.read_text(encoding="utf-8-sig"))
    packets: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("packets"), list):
        packets = [item for item in payload["packets"] if isinstance(item, dict)]
    elif isinstance(payload, list):
        packets = [item for item in payload if isinstance(item, dict)]
    else:
        raise TranscriptionError(f"unsupported game info format in {game_info_file}")

    target_date = str(audio_row.get("date", ""))
    target_away = str(audio_row.get("away", "")).strip().casefold()
    target_home = str(audio_row.get("home", "")).strip().casefold()

    for packet in packets:
        if str(packet.get("date", "")) != target_date:
            continue
        if str(packet.get("away", "")).strip().casefold() != target_away:
            continue
        if str(packet.get("home", "")).strip().casefold() != target_home:
            continue
        return packet

    raise TranscriptionError(
        "matching game packet not found for audio row "
        f"{target_date} {audio_row.get('away','')} @ {audio_row.get('home','')}"
    )


def _build_transcription_prompt(
    *,
    audio_row: dict[str, Any],
    game_packet: dict[str, Any],
    glossary_text: str,
) -> str:
    compact_packet = {
        "date": game_packet.get("date", ""),
        "game_id": game_packet.get("game_id", ""),
        "away": game_packet.get("away", ""),
        "home": game_packet.get("home", ""),
        "rosters": game_packet.get("rosters", {}),
        "commentary": game_packet.get("commentary", {}),
    }
    prompt_sections = [
        "Transcribe this NBA game audio accurately.",
        "Use provided names/terms to improve spelling. Do not invent words not present in audio.",
        f"Feed metadata: date={audio_row.get('date','')}, away={audio_row.get('away','')}, "
        f"home={audio_row.get('home','')}, feed_label={audio_row.get('feed_label','')}.",
        "Game info packet (JSON):",
        json.dumps(compact_packet, ensure_ascii=False, indent=2, sort_keys=True),
        "Basketball glossary:",
        glossary_text,
    ]
    return "\n\n".join(prompt_sections)


def _call_openai_transcription(
    *,
    session: requests.Session | Any,
    api_key: str,
    model: str,
    audio_path: Path,
    prompt: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    mime_type, _ = mimetypes.guess_type(str(audio_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    with audio_path.open("rb") as handle:
        response = session.post(
            url,
            headers=headers,
            data={
                "model": model,
                "prompt": prompt,
            },
            files={"file": (audio_path.name, handle, mime_type)},
            timeout=timeout_seconds,
        )
    try:
        response.raise_for_status()
    except Exception as exc:
        body = ""
        try:
            body = response.text
        except Exception:
            body = ""
        raise TranscriptionError(f"OpenAI transcription request failed: {exc}. body={body[:500]}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise TranscriptionError("OpenAI transcription response was not JSON") from exc
    if not isinstance(payload, dict):
        raise TranscriptionError("OpenAI transcription response must be a JSON object")
    return payload


def _create_audio_clip_ffmpeg(input_path: Path, output_path: Path, max_seconds: float, ffmpeg_bin: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-t",
        f"{max_seconds:g}",
        "-vn",
        str(output_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise TranscriptionError(f"ffmpeg clip failed: {err[:500]}")
    if not output_path.exists():
        raise TranscriptionError("ffmpeg clip failed: output file was not created")


def _probe_duration_seconds(audio_path: Path, ffprobe_bin: str) -> float:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise TranscriptionError(f"ffprobe failed: {err[:500]}")
    value = (completed.stdout or "").strip()
    try:
        duration = float(value)
    except ValueError as exc:
        raise TranscriptionError(f"ffprobe returned invalid duration: '{value}'") from exc
    if duration <= 0:
        raise TranscriptionError(f"ffprobe returned non-positive duration: {duration}")
    return duration


def _build_chunk_specs(
    *,
    audio_path: Path,
    chunk_seconds: float,
    chunk_overlap_seconds: float,
    ffprobe_bin: str,
    duration_prober: DurationProberFn,
) -> list[dict[str, float | None]]:
    if chunk_seconds <= 0:
        return [{"start_seconds": None, "end_seconds": None}]
    duration = duration_prober(audio_path, ffprobe_bin)
    if duration <= chunk_seconds:
        return [{"start_seconds": None, "end_seconds": None}]

    specs: list[dict[str, float | None]] = []
    start = 0.0
    while start < duration:
        end = min(duration, start + chunk_seconds)
        specs.append(
            {
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
            }
        )
        if end >= duration:
            break
        next_start = end - chunk_overlap_seconds
        if next_start <= start:
            next_start = end
        start = next_start
    return specs


def _build_chunk_prompt(
    *,
    prompt: str,
    index: int,
    total: int,
    spec: dict[str, float | None],
) -> str:
    if spec["start_seconds"] is None or spec["end_seconds"] is None:
        return prompt
    return (
        f"{prompt}\n\n"
        f"Chunk metadata: chunk {index}/{total}, "
        f"audio_range_seconds={spec['start_seconds']}..{spec['end_seconds']}."
    )


def _chunk_progress_percent(*, index: int, total_chunks: int) -> int:
    if total_chunks <= 0:
        return 60
    start = 60
    end = 92
    ratio = (index - 1) / max(1, total_chunks - 1)
    return int(round(start + ratio * (end - start)))


def _merge_chunk_texts(texts: list[str]) -> str:
    if not texts:
        return ""
    merged = texts[0]
    for nxt in texts[1:]:
        overlap = _longest_suffix_prefix_overlap(merged, nxt, max_chars=250)
        if overlap > 0:
            merged = f"{merged}\n{nxt[overlap:].lstrip()}"
        else:
            merged = f"{merged}\n{nxt}"
    return merged.strip()


def _longest_suffix_prefix_overlap(left: str, right: str, max_chars: int) -> int:
    max_len = min(len(left), len(right), max_chars)
    for size in range(max_len, 0, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def _build_correction_entities(*, audio_row: dict[str, Any], game_packet: dict[str, Any]) -> list[str]:
    entities: list[str] = []

    def add(value: str) -> None:
        text = " ".join(value.split()).strip()
        if not text:
            return
        if text not in entities:
            entities.append(text)

    rosters = game_packet.get("rosters", {})
    if isinstance(rosters, dict):
        for side in ("away", "home"):
            players = rosters.get(side, [])
            if not isinstance(players, list):
                continue
            for player in players:
                if not isinstance(player, dict):
                    continue
                name = player.get("name")
                if isinstance(name, str):
                    add(name)

    commentary = game_packet.get("commentary", {})
    if isinstance(commentary, dict):
        commentators = commentary.get("commentators", [])
        if isinstance(commentators, list):
            for item in commentators:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str):
                        add(name)
                elif isinstance(item, str):
                    add(item)

    for team_name in (
        str(audio_row.get("away", "")),
        str(audio_row.get("home", "")),
        str(game_packet.get("away", "")),
        str(game_packet.get("home", "")),
    ):
        nickname = _team_nickname_from_full_name(team_name)
        if nickname:
            add(nickname)

    entities.sort(key=lambda text: (-len(_split_words(text)), -len(text), text))
    return entities


def _team_nickname_from_full_name(full_name: str) -> str:
    normalized = " ".join(full_name.lower().split())
    if not normalized:
        return ""
    direct = NBA_TEAM_NICKNAMES.get(normalized)
    if direct:
        return direct
    parts = full_name.split()
    if len(parts) <= 1:
        return full_name.strip()
    if len(parts) >= 3:
        lowered = [part.lower() for part in parts[:2]]
        if lowered in (["los", "angeles"], ["new", "york"], ["new", "orleans"], ["oklahoma", "city"], ["golden", "state"], ["san", "antonio"]):
            return " ".join(parts[2:]).strip()
    return " ".join(parts[1:]).strip()


def _apply_deterministic_entity_corrections(text: str, entities: list[str]) -> tuple[str, list[dict[str, Any]]]:
    if not text.strip() or not entities:
        return text, []

    word_matches = list(re.finditer(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text))
    if not word_matches:
        return text, []
    words_norm = [_normalize_word(match.group(0)) for match in word_matches]

    entity_specs: list[dict[str, Any]] = []
    for entity in entities:
        norm = _normalize_phrase(entity)
        words = _split_words(norm)
        if not words:
            continue
        entity_specs.append(
            {
                "entity": entity,
                "norm": norm,
                "word_count": len(words),
            }
        )
    if not entity_specs:
        return text, []

    proposals: list[dict[str, Any]] = []
    for entity_spec in entity_specs:
        n = int(entity_spec["word_count"])
        for idx in range(0, len(word_matches) - n + 1):
            candidate_norm = " ".join(words_norm[idx : idx + n]).strip()
            if not candidate_norm:
                continue
            start = word_matches[idx].start()
            end = word_matches[idx + n - 1].end()
            original = text[start:end]
            if candidate_norm == entity_spec["norm"]:
                if original == str(entity_spec["entity"]):
                    continue
                score = 1.0
            else:
                score = difflib.SequenceMatcher(None, candidate_norm, entity_spec["norm"]).ratio()
                threshold = 0.82 if n == 1 else 0.8
                if score < threshold:
                    continue
                if candidate_norm[0] != entity_spec["norm"][0]:
                    continue
            proposals.append(
                {
                    "start": start,
                    "end": end,
                    "replacement": entity_spec["entity"],
                    "original": original,
                    "score": score,
                }
            )

    proposals.sort(key=lambda item: (-float(item["score"]), -(item["end"] - item["start"]), item["start"]))
    selected: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for proposal in proposals:
        start = int(proposal["start"])
        end = int(proposal["end"])
        if any(not (end <= occ_start or start >= occ_end) for occ_start, occ_end in occupied):
            continue
        occupied.append((start, end))
        selected.append(proposal)

    selected.sort(key=lambda item: int(item["start"]))
    if not selected:
        return text, []

    corrected = text
    for proposal in reversed(selected):
        start = int(proposal["start"])
        end = int(proposal["end"])
        corrected = corrected[:start] + str(proposal["replacement"]) + corrected[end:]

    replacements = [
        {
            "from": str(item["original"]),
            "to": str(item["replacement"]),
            "score": round(float(item["score"]), 4),
            "start": int(item["start"]),
        }
        for item in selected
        if str(item["original"]) != str(item["replacement"])
    ]
    return corrected, replacements


def _extract_transcript_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text
    transcript = payload.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript
    raise TranscriptionError("transcription response missing 'text'")


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise TranscriptionError(f"expected JSON list in {path}")
    return [item for item in payload if isinstance(item, dict)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_positive_float(value: float | None, *, field_name: str) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric <= 0:
        raise TranscriptionError(f"{field_name} must be > 0 when provided")
    return numeric


def _normalize_chunk_seconds(value: float) -> float:
    numeric = float(value)
    if numeric < 0:
        raise TranscriptionError("chunk_seconds must be >= 0")
    return numeric


def _normalize_overlap(*, chunk_overlap_seconds: float, chunk_seconds: float) -> float:
    overlap = float(chunk_overlap_seconds)
    if overlap < 0:
        raise TranscriptionError("chunk_overlap_seconds must be >= 0")
    if chunk_seconds > 0 and overlap >= chunk_seconds:
        raise TranscriptionError("chunk_overlap_seconds must be smaller than chunk_seconds")
    return overlap


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    percent: int,
    stage: str,
    detail: str | None = None,
) -> None:
    if callback is None:
        return
    event = {"event": "transcription_progress", "percent": int(percent), "stage": stage}
    if detail:
        event["detail"] = detail
    callback(event)


def _make_repo_temp_clip_path(*, output_path: Path, source_path: Path, max_seconds: float) -> Path:
    tmp_dir = output_path.parent / "_tmp_transcribe_clips"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix if source_path.suffix else ".mp3"
    file_name = (
        f"{source_path.stem}_first_{int(max_seconds)}s_"
        f"{uuid.uuid4().hex[:8]}{suffix}"
    )
    return tmp_dir / file_name


def _make_repo_temp_chunk_path(*, output_path: Path, source_path: Path, index: int) -> Path:
    tmp_dir = output_path.parent / "_tmp_transcribe_chunks"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix if source_path.suffix else ".mp3"
    file_name = f"{source_path.stem}_chunk_{index:03d}_{uuid.uuid4().hex[:8]}{suffix}"
    return tmp_dir / file_name


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        return


def _safe_rmdir(path: Path) -> None:
    try:
        if path.exists() and not any(path.iterdir()):
            path.rmdir()
    except Exception:
        return


def _normalize_word(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_phrase(value: str) -> str:
    parts = [_normalize_word(word) for word in _split_words(value)]
    parts = [part for part in parts if part]
    return " ".join(parts)


def _split_words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", value)


def _default_transcript_output_path(*, audio_id: str, max_seconds: float | None) -> Path:
    if max_seconds is None:
        filename = f"{audio_id}.json"
    else:
        seconds = float(max_seconds)
        if abs(seconds - round(seconds)) < 1e-9:
            test_token = f"{int(round(seconds))}"
        else:
            # Keep deterministic filename token for fractional seconds.
            test_token = f"{seconds:g}".replace(".", "_")
        filename = f"{audio_id}.test{test_token}s.json"
    return Path("data") / "transcripts" / filename
