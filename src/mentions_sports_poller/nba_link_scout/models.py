from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Game:
    date: str
    home: str
    away: str
    game_id: str
    url_candidates: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinkConstraints:
    must_contain: tuple[str, ...] = ()
    require_same_domain: bool = False
    allowed_schemes: tuple[str, ...] = ("http", "https")


@dataclass(frozen=True)
class LinkSearchRule:
    base_url: str | None
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    collect_targets: tuple[str, ...] = (
        "a.href",
        "link.href",
        "iframe.src",
        "video.src",
        "source.src",
    )
    constraints: LinkConstraints = field(default_factory=LinkConstraints)


@dataclass(frozen=True)
class TargetSiteRule:
    name: str
    domain: str
    url_templates: tuple[str, ...]
    required_params: tuple[str, ...] = ()
    link_search_rule: LinkSearchRule = field(default_factory=lambda: LinkSearchRule(base_url=None))


@dataclass(frozen=True)
class ExtractionResult:
    found_links: tuple[str, ...]
    method_used: str
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduleFieldMap:
    game_id: str
    date: str
    home: str
    away: str


@dataclass(frozen=True)
class ScheduleSourceConfig:
    provider: str
    url_template: str | None = None
    request_params: dict[str, str] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    games_path: str = "games"
    field_map: ScheduleFieldMap = field(
        default_factory=lambda: ScheduleFieldMap(
            game_id="gameId",
            date="date",
            home="home",
            away="away",
        )
    )
    date_format: str = "%Y-%m-%d"
    start_offset_days: int = 0
    end_offset_days: int = 0
    file_path: str | None = None
    dry_run_games: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class FallbackExtractorConfig:
    module_path: str
    function_name: str
    function_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HttpSettings:
    user_agent: str = "nba-link-scout/0.1"
    request_headers: dict[str, str] = field(default_factory=dict)
    follow_redirects: bool = True
    target_page_fetch_mode: str = "http"
    playwright_headless: bool = True
    playwright_wait_until: str = "domcontentloaded"
    playwright_timeout_seconds: float = 60.0
    timeout_seconds: float = 15.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.35


@dataclass(frozen=True)
class ScoutConfig:
    schedule_source: ScheduleSourceConfig
    target_sites: tuple[TargetSiteRule, ...]
    team_filter: tuple[str, ...] = ()
    fallback_extractor: FallbackExtractorConfig | None = None
    fallback_extractors: tuple[FallbackExtractorConfig, ...] = ()
    video_link_rule: LinkSearchRule | None = None
    daily_video_output_path: str | None = None
    http: HttpSettings = field(default_factory=HttpSettings)


@dataclass(frozen=True)
class RunOptions:
    requested_date: date
    dry_run: bool = False
    timeout_seconds: float | None = None
    max_retries: int | None = None
    daily_video_output_path_override: str | None = None


@dataclass(frozen=True)
class UrlCandidate:
    game: Game
    target_site_name: str
    page_url: str
    link_search_rule: LinkSearchRule
