from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    FallbackExtractorConfig,
    HttpSettings,
    LinkConstraints,
    LinkSearchRule,
    ScheduleFieldMap,
    ScheduleSourceConfig,
    ScoutConfig,
    TargetSiteRule,
)


class ConfigError(ValueError):
    """Raised when the scout config is invalid."""


def load_scout_config(path: str | Path) -> ScoutConfig:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ConfigError("config root must be an object")

    schedule_source = _parse_schedule_source(payload.get("schedule_source"))
    target_sites = _parse_target_sites(payload.get("target_sites"))
    team_filter = _to_str_tuple(payload.get("team_filter", ()))

    fallback_cfg_raw = payload.get("fallback_extractor")
    fallback_extractor = None
    if fallback_cfg_raw is not None:
        fallback_extractor = _parse_fallback_extractor(fallback_cfg_raw)
    fallback_extractors = _parse_fallback_extractors(payload.get("fallback_extractors", ()))
    if not fallback_extractors and fallback_extractor is not None:
        fallback_extractors = (fallback_extractor,)

    video_link_rule = None
    video_link_rule_raw = payload.get("video_link_rule")
    if video_link_rule_raw is not None:
        video_link_rule = _parse_link_rule(
            video_link_rule_raw,
            location="video_link_rule",
            with_collect_targets=False,
        )

    http = _parse_http(payload.get("http"))

    return ScoutConfig(
        schedule_source=schedule_source,
        target_sites=target_sites,
        team_filter=team_filter,
        fallback_extractor=fallback_extractor,
        fallback_extractors=fallback_extractors,
        video_link_rule=video_link_rule,
        daily_video_output_path=_optional_str(payload.get("daily_video_output_path")),
        http=http,
    )


def _parse_schedule_source(raw: Any) -> ScheduleSourceConfig:
    if not isinstance(raw, dict):
        raise ConfigError("schedule_source must be an object")

    provider = _require_str(raw, "provider", "schedule_source")
    field_map_raw = raw.get("field_map")
    if not isinstance(field_map_raw, dict):
        raise ConfigError("schedule_source.field_map must be an object")

    field_map = ScheduleFieldMap(
        game_id=_require_str(field_map_raw, "game_id", "schedule_source.field_map"),
        date=_require_str(field_map_raw, "date", "schedule_source.field_map"),
        home=_require_str(field_map_raw, "home", "schedule_source.field_map"),
        away=_require_str(field_map_raw, "away", "schedule_source.field_map"),
    )

    url_template = _optional_str(raw.get("url_template"))
    if provider == "http_json" and not url_template:
        raise ConfigError("schedule_source.url_template is required for provider=http_json")
    if provider == "file_json" and not _optional_str(raw.get("file_path")):
        raise ConfigError("schedule_source.file_path is required for provider=file_json")

    request_params = _to_str_dict(raw.get("request_params", {}), "schedule_source.request_params")
    request_headers = _to_str_dict(raw.get("request_headers", {}), "schedule_source.request_headers")
    dry_run_games_raw = raw.get("dry_run_games")
    if dry_run_games_raw is None:
        dry_run_games: tuple[dict[str, Any], ...] = ()
    else:
        if not isinstance(dry_run_games_raw, (list, tuple)):
            raise ConfigError("schedule_source.dry_run_games must be a list")
        dry_run_games = tuple(item for item in dry_run_games_raw if isinstance(item, dict))

    return ScheduleSourceConfig(
        provider=provider,
        url_template=url_template,
        request_params=request_params,
        request_headers=request_headers,
        games_path=_optional_str(raw.get("games_path")) or "games",
        field_map=field_map,
        date_format=_optional_str(raw.get("date_format")) or "%Y-%m-%d",
        start_offset_days=_to_int(raw.get("start_offset_days", 0), "schedule_source.start_offset_days"),
        end_offset_days=_to_int(raw.get("end_offset_days", 0), "schedule_source.end_offset_days"),
        file_path=_optional_str(raw.get("file_path")),
        dry_run_games=dry_run_games,
    )


def _parse_target_sites(raw: Any) -> tuple[TargetSiteRule, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("target_sites must be a non-empty list")

    parsed: list[TargetSiteRule] = []
    for index, site_raw in enumerate(raw):
        location = f"target_sites[{index}]"
        if not isinstance(site_raw, dict):
            raise ConfigError(f"{location} must be an object")
        link_rule_raw = site_raw.get("link_search_rule")
        link_rule = _parse_link_rule(link_rule_raw, location=f"{location}.link_search_rule")
        parsed.append(
            TargetSiteRule(
                name=_require_str(site_raw, "name", location),
                domain=_require_str(site_raw, "domain", location),
                url_templates=_to_str_tuple(site_raw.get("url_templates", ())),
                required_params=_to_str_tuple(site_raw.get("required_params", ())),
                link_search_rule=link_rule,
            )
        )

    for site in parsed:
        if not site.url_templates and site.link_search_rule.base_url is None:
            raise ConfigError(
                f"target site '{site.name}' must provide url_templates or link_search_rule.base_url"
            )

    return tuple(parsed)


def _parse_fallback_extractor(raw: Any) -> FallbackExtractorConfig:
    if not isinstance(raw, dict):
        raise ConfigError("fallback_extractor must be an object")
    kwargs = raw.get("function_kwargs", {})
    if kwargs is None:
        kwargs = {}
    if not isinstance(kwargs, dict):
        raise ConfigError("fallback_extractor.function_kwargs must be an object")

    return FallbackExtractorConfig(
        module_path=_require_str(raw, "module_path", "fallback_extractor"),
        function_name=_require_str(raw, "function_name", "fallback_extractor"),
        function_kwargs=kwargs,
    )


def _parse_fallback_extractors(raw: Any) -> tuple[FallbackExtractorConfig, ...]:
    if raw is None:
        return ()
    if isinstance(raw, dict):
        return (_parse_fallback_extractor(raw),)
    if not isinstance(raw, (list, tuple)):
        raise ConfigError("fallback_extractors must be a list")
    parsed: list[FallbackExtractorConfig] = []
    for item in raw:
        parsed.append(_parse_fallback_extractor(item))
    return tuple(parsed)


def _parse_link_rule(raw: Any, *, location: str, with_collect_targets: bool = True) -> LinkSearchRule:
    if not isinstance(raw, dict):
        raise ConfigError(f"{location} must be an object")
    link_constraints_raw = raw.get("constraints", {})
    if not isinstance(link_constraints_raw, dict):
        raise ConfigError(f"{location}.constraints must be an object")
    collect_targets_default = ()
    if with_collect_targets:
        collect_targets_default = ("a.href", "link.href", "iframe.src", "video.src", "source.src")
    return LinkSearchRule(
        base_url=_optional_str(raw.get("base_url")),
        include_patterns=_to_str_tuple(raw.get("include_patterns", ())),
        exclude_patterns=_to_str_tuple(raw.get("exclude_patterns", ())),
        collect_targets=_to_str_tuple(raw.get("collect_targets", collect_targets_default)),
        constraints=LinkConstraints(
            must_contain=_to_str_tuple(link_constraints_raw.get("must_contain", ())),
            require_same_domain=bool(link_constraints_raw.get("require_same_domain", False)),
            allowed_schemes=_to_str_tuple(link_constraints_raw.get("allowed_schemes", ("http", "https"))),
        ),
    )


def _parse_http(raw: Any) -> HttpSettings:
    if raw is None:
        return HttpSettings()
    if not isinstance(raw, dict):
        raise ConfigError("http must be an object")
    return HttpSettings(
        user_agent=_optional_str(raw.get("user_agent")) or "nba-link-scout/0.1",
        timeout_seconds=_to_float(raw.get("timeout_seconds", 15.0), "http.timeout_seconds"),
        max_retries=_to_int(raw.get("max_retries", 3), "http.max_retries"),
        backoff_base_seconds=_to_float(
            raw.get("backoff_base_seconds", 0.35),
            "http.backoff_base_seconds",
        ),
    )


def _require_str(payload: dict[str, Any], key: str, location: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location}.{key} must be a non-empty string")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"expected string but got {type(value).__name__}")
    stripped = value.strip()
    return stripped if stripped else None


def _to_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise ConfigError("expected a string or list of strings")
    items: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            raise ConfigError("all list values must be strings")
        stripped = raw.strip()
        if stripped:
            items.append(stripped)
    return tuple(items)


def _to_str_dict(value: Any, location: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{location} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"{location} keys must be strings")
        if not isinstance(item, str):
            raise ConfigError(f"{location}.{key} must be a string")
        result[key] = item
    return result


def _to_int(value: Any, location: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{location} must be an int") from exc


def _to_float(value: Any, location: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{location} must be a number") from exc
