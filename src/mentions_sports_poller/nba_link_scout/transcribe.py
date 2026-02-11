from __future__ import annotations

from contextlib import ExitStack
import json
import mimetypes
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

ProgressCallback = Callable[[dict[str, Any]], None]
ClipperFn = Callable[[Path, Path, float, str], None]


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
    progress_callback: ProgressCallback | None = None,
    clipper: ClipperFn | None = None,
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
        output_path = Path("data") / "transcripts" / f"{audio_id}.json"
    output_path = Path(output_path)

    normalized_max_seconds = _normalize_max_seconds(max_seconds)
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
    audio_for_transcription = audio_path
    try:
        with ExitStack() as stack:
            if normalized_max_seconds is not None:
                _emit_progress(
                    progress_callback,
                    percent=30,
                    stage="clipping_start",
                    detail=f"first {normalized_max_seconds:g}s",
                )
                tmp_dir = output_path.parent / "_tmp_transcribe_clips"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                suffix = audio_path.suffix if audio_path.suffix else ".mp3"
                clip_name = (
                    f"{audio_path.stem}_first_{int(normalized_max_seconds)}s_"
                    f"{uuid.uuid4().hex[:8]}{suffix}"
                )
                clip_path = tmp_dir / clip_name
                active_clipper(audio_path, clip_path, normalized_max_seconds, ffmpeg_bin)
                audio_for_transcription = clip_path
                stack.callback(_safe_unlink, clip_path)
                stack.callback(_safe_rmdir, tmp_dir)
                _emit_progress(progress_callback, percent=45, stage="clipping_done")
            else:
                _emit_progress(progress_callback, percent=45, stage="audio_ready")

            _emit_progress(progress_callback, percent=60, stage="api_request_started")
            api_response = _call_openai_transcription(
                session=active_session,
                api_key=api_key,
                model=model,
                audio_path=audio_for_transcription,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
            _emit_progress(progress_callback, percent=90, stage="api_response_received")
    finally:
        if owns_session:
            active_session.close()

    transcript_text = _extract_transcript_text(api_response)
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
        "context_sources": {
            "game_info_file": str(Path(game_info_file)),
            "glossary_file": str(Path(glossary_file)),
        },
        "transcript_text": transcript_text,
        "api_response": api_response,
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


def _normalize_max_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric <= 0:
        raise TranscriptionError("max_seconds must be > 0 when provided")
    return numeric


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
