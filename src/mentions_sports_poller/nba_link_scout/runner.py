from __future__ import annotations

import logging
from dataclasses import asdict, replace
from typing import Any

from .fallback import FallbackExtractorAdapter
from .fetcher import HttpFetcher
from .game_selection import filter_games_for_date
from .link_finder import apply_link_filters, extract_links_from_html, normalize_urls
from .models import ExtractionResult, RunOptions, ScoutConfig
from .schedule import make_schedule_provider, make_schedule_query
from .url_builder import build_urls_for_game


def run_link_scout(
    *,
    config: ScoutConfig,
    options: RunOptions,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    timeout = options.timeout_seconds if options.timeout_seconds is not None else config.http.timeout_seconds
    retries = options.max_retries if options.max_retries is not None else config.http.max_retries

    query = make_schedule_query(options.requested_date, config.schedule_source)
    result_payload: dict[str, Any] = {
        "requested_date": options.requested_date.isoformat(),
        "dry_run": options.dry_run,
        "schedule_requests": [],
        "games_total": 0,
        "games_selected": 0,
        "results": [],
        "errors": [],
    }

    fallback_adapters = [
        FallbackExtractorAdapter(config=fallback_cfg, logger=log)
        for fallback_cfg in config.fallback_extractors
    ]

    with HttpFetcher(
        timeout_seconds=timeout,
        max_retries=retries,
        backoff_base_seconds=config.http.backoff_base_seconds,
        user_agent=config.http.user_agent,
        logger=log,
    ) as fetcher:
        schedule_provider = make_schedule_provider(
            config=config.schedule_source,
            fetcher=None if options.dry_run else fetcher,
            logger=log,
        )
        result_payload["schedule_requests"] = schedule_provider.describe_requests(query)

        if options.dry_run:
            games = schedule_provider.dry_run_games(query)
        else:
            games = schedule_provider.fetch_games(query)

        selected_games = filter_games_for_date(
            games,
            requested_date=options.requested_date,
            team_filter=config.team_filter,
        )
        result_payload["games_total"] = len(games)
        result_payload["games_selected"] = len(selected_games)

        for game in selected_games:
            url_candidates, url_errors = build_urls_for_game(game, config.target_sites, logger=log)
            result_payload["errors"].extend(url_errors)
            game_urls = tuple(candidate.page_url for candidate in url_candidates)
            game_with_urls = replace(game, url_candidates=game_urls)
            for candidate in url_candidates:
                if options.dry_run:
                    extraction = ExtractionResult(
                        found_links=(),
                        method_used="html",
                        debug={
                            "planned_only": True,
                            "would_fetch": candidate.page_url,
                            "collect_targets": list(candidate.link_search_rule.collect_targets),
                            "include_patterns": list(candidate.link_search_rule.include_patterns),
                            "exclude_patterns": list(candidate.link_search_rule.exclude_patterns),
                        },
                    )
                    result_payload["results"].append(
                        {
                            "game": asdict(game_with_urls),
                            "target_site": candidate.target_site_name,
                            "page_url": candidate.page_url,
                            "extraction": asdict(extraction),
                        }
                    )
                    continue

                url_result = _process_candidate(
                    candidate=candidate,
                    fetcher=fetcher,
                    fallback_adapters=fallback_adapters,
                    video_link_rule=config.video_link_rule,
                    logger=log,
                )
                result_payload["results"].append(
                    {
                        "game": asdict(game_with_urls),
                        "target_site": candidate.target_site_name,
                        "page_url": candidate.page_url,
                        "extraction": asdict(url_result),
                    }
                )

    result_payload["daily_video_rows"] = _build_daily_video_rows(result_payload["results"])
    return result_payload


def _process_candidate(
    *,
    candidate: Any,
    fetcher: HttpFetcher,
    fallback_adapters: list[FallbackExtractorAdapter],
    video_link_rule: Any | None,
    logger: logging.Logger,
) -> ExtractionResult:
    try:
        response = fetcher.get_text(candidate.page_url)
    except Exception as exc:
        message = f"failed to fetch {candidate.page_url}: {exc}"
        logger.error(message)
        return ExtractionResult(found_links=(), method_used="html", debug={"error": message})

    html_links = extract_links_from_html(
        response.text,
        base_url=response.url,
        rule=candidate.link_search_rule,
    )
    debug: dict[str, Any] = {
        "status_code": response.status_code,
        "html_matches": len(html_links),
    }

    if video_link_rule is None and html_links:
        return ExtractionResult(
            found_links=tuple(html_links),
            method_used="html",
            debug=debug,
        )

    final_filter_rule = video_link_rule or candidate.link_search_rule
    if video_link_rule is not None:
        direct_video_links = apply_link_filters(
            html_links,
            base_url=response.url,
            rule=video_link_rule,
        )
        debug["direct_video_matches"] = len(direct_video_links)
        if direct_video_links:
            return ExtractionResult(
                found_links=tuple(direct_video_links),
                method_used="html",
                debug=debug,
            )

    if not fallback_adapters:
        return ExtractionResult(found_links=(), method_used="html", debug=debug)

    # Try extractors on the source page and on intermediary links found in the source HTML.
    extraction_targets = _unique_preserve_order([candidate.page_url, *html_links])
    collected: list[str] = []
    fallback_attempts: list[dict[str, Any]] = []
    for target_url in extraction_targets:
        for adapter in fallback_adapters:
            adapter_config = getattr(adapter, "config", None)
            module_path = getattr(adapter_config, "module_path", adapter.__class__.__name__)
            function_name = getattr(adapter_config, "function_name", "extract")
            attempt_debug: dict[str, Any] = {
                "target_url": target_url,
                "module_path": module_path,
                "function_name": function_name,
            }
            try:
                raw_fallback_links = adapter.extract(
                    page_url=target_url,
                    html=response.text if target_url == candidate.page_url else "",
                )
                normalized = normalize_urls(raw_fallback_links, base_url=target_url)
                filtered = apply_link_filters(normalized, base_url=target_url, rule=final_filter_rule)
                attempt_debug["raw_count"] = len(raw_fallback_links)
                attempt_debug["filtered_count"] = len(filtered)
                collected.extend(filtered)
            except Exception as exc:
                message = (
                    "fallback extractor failed "
                    f"({module_path}:{function_name}) "
                    f"on {target_url}: {exc}"
                )
                attempt_debug["error"] = str(exc)
                logger.error(message)
            fallback_attempts.append(attempt_debug)

    unique_filtered = tuple(_unique_preserve_order(collected))
    debug["fallback_attempts"] = fallback_attempts
    debug["fallback_filtered_count"] = len(unique_filtered)
    return ExtractionResult(
        found_links=unique_filtered,
        method_used="fallback",
        debug=debug,
    )


def _build_daily_video_rows(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in results:
        game = item.get("game", {})
        extraction = item.get("extraction", {})
        date_only = str(game.get("date", ""))[:10]
        home = str(game.get("home", ""))
        away = str(game.get("away", ""))
        for video_url in extraction.get("found_links", []):
            if not isinstance(video_url, str):
                continue
            key = (date_only, home, away, video_url)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "date": date_only,
                    "home": home,
                    "away": away,
                    "video_url": video_url,
                    "source_page": str(item.get("page_url", "")),
                    "target_site": str(item.get("target_site", "")),
                    "method_used": str(extraction.get("method_used", "")),
                }
            )
    rows.sort(key=lambda row: (row["date"], row["away"], row["home"], row["video_url"]))
    return rows


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
