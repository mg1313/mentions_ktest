from __future__ import annotations

import logging
from contextlib import ExitStack
from dataclasses import asdict, replace
from typing import Any

from .fallback import FallbackExtractorAdapter
from .fetcher import HttpFetcher
from .game_selection import filter_games_for_date
from .link_finder import apply_link_filters, extract_links_from_html, normalize_urls
from .models import ExtractionResult, RunOptions, ScoutConfig
from .playwright_fetcher import PlaywrightFetcher
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
    disabled_fallback_keys: set[str] = set()
    fallback_failure_counts: dict[str, int] = {}

    with ExitStack() as stack:
        fetcher = stack.enter_context(
            HttpFetcher(
                timeout_seconds=timeout,
                max_retries=retries,
                backoff_base_seconds=config.http.backoff_base_seconds,
                user_agent=config.http.user_agent,
                request_headers=config.http.request_headers,
                follow_redirects=config.http.follow_redirects,
                logger=log,
            )
        )
        target_page_fetcher = _build_target_page_fetcher(
            stack=stack,
            config=config,
            options=options,
            http_fetcher=fetcher,
            logger=log,
        )
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
                    fetcher=target_page_fetcher,
                    fallback_adapters=fallback_adapters,
                    video_link_rule=config.video_link_rule,
                    disabled_fallback_keys=disabled_fallback_keys,
                    fallback_failure_counts=fallback_failure_counts,
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
    result_payload["daily_video_pairs"] = _build_daily_video_pairs(result_payload["results"])
    return result_payload


def _process_candidate(
    *,
    candidate: Any,
    fetcher: Any,
    fallback_adapters: list[FallbackExtractorAdapter],
    video_link_rule: Any | None,
    disabled_fallback_keys: set[str] | None = None,
    fallback_failure_counts: dict[str, int] | None = None,
    logger: logging.Logger,
) -> ExtractionResult:
    final_filter_rule = video_link_rule or candidate.link_search_rule
    try:
        response = fetcher.get_text(candidate.page_url)
    except Exception as exc:
        message = f"failed to fetch {candidate.page_url}: {exc}"
        logger.error(message)
        if not fallback_adapters:
            return ExtractionResult(found_links=(), method_used="html", debug={"error": message})
        fallback_links, fallback_debug, fallback_link_sources = _run_fallback_extractors(
            extraction_targets=[candidate.page_url],
            fallback_adapters=fallback_adapters,
            final_filter_rule=final_filter_rule,
            source_html_by_url={},
            disabled_fallback_keys=disabled_fallback_keys,
            fallback_failure_counts=fallback_failure_counts,
            logger=logger,
        )
        debug = {
            "error": message,
            "fallback_attempts": fallback_debug,
            "fallback_link_sources": fallback_link_sources,
        }
        return ExtractionResult(found_links=fallback_links, method_used="fallback", debug=debug)

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
                debug={
                    **debug,
                    "direct_link_sources": [
                        {"video_url": link, "extracted_from_url": response.url}
                        for link in direct_video_links
                    ],
                },
            )

    if not fallback_adapters:
        return ExtractionResult(found_links=(), method_used="html", debug=debug)

    # Try extractors on the source page and on intermediary links found in the source HTML.
    extraction_targets = _unique_preserve_order([candidate.page_url, *html_links])
    unique_filtered, fallback_attempts, fallback_link_sources = _run_fallback_extractors(
        extraction_targets=extraction_targets,
        fallback_adapters=fallback_adapters,
        final_filter_rule=final_filter_rule,
        source_html_by_url={candidate.page_url: response.text},
        disabled_fallback_keys=disabled_fallback_keys,
        fallback_failure_counts=fallback_failure_counts,
        logger=logger,
    )
    debug["fallback_attempts"] = fallback_attempts
    debug["fallback_link_sources"] = fallback_link_sources
    debug["fallback_filtered_count"] = len(unique_filtered)
    return ExtractionResult(
        found_links=unique_filtered,
        method_used="fallback",
        debug=debug,
    )


def _run_fallback_extractors(
    *,
    extraction_targets: list[str],
    fallback_adapters: list[FallbackExtractorAdapter],
    final_filter_rule: Any,
    source_html_by_url: dict[str, str],
    disabled_fallback_keys: set[str] | None,
    fallback_failure_counts: dict[str, int] | None,
    logger: logging.Logger,
) -> tuple[tuple[str, ...], list[dict[str, Any]], list[dict[str, str]]]:
    collected: list[str] = []
    collected_sources: list[dict[str, str]] = []
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
            adapter_key = f"{module_path}:{function_name}"
            if disabled_fallback_keys is not None and adapter_key in disabled_fallback_keys:
                attempt_debug["skipped"] = "adapter_disabled"
                fallback_attempts.append(attempt_debug)
                continue
            try:
                raw_fallback_links = adapter.extract(
                    page_url=target_url,
                    html=source_html_by_url.get(target_url, ""),
                )
                normalized = normalize_urls(raw_fallback_links, base_url=target_url)
                filtered = apply_link_filters(normalized, base_url=target_url, rule=final_filter_rule)
                attempt_debug["raw_count"] = len(raw_fallback_links)
                attempt_debug["filtered_count"] = len(filtered)
                attempt_debug["filtered_urls"] = filtered
                collected.extend(filtered)
                for link in filtered:
                    collected_sources.append(
                        {"video_url": link, "extracted_from_url": target_url}
                    )
            except Exception as exc:
                fail_count = 1
                if fallback_failure_counts is not None:
                    fail_count = fallback_failure_counts.get(adapter_key, 0) + 1
                    fallback_failure_counts[adapter_key] = fail_count
                message = (
                    "fallback extractor failed "
                    f"({module_path}:{function_name}) "
                    f"on {target_url}: {exc}"
                )
                attempt_debug["error"] = str(exc)
                attempt_debug["failure_count"] = fail_count
                if (
                    disabled_fallback_keys is not None
                    and _should_disable_fallback_adapter(
                        module_path=module_path,
                        error=exc,
                        failure_count=fail_count,
                    )
                ):
                    disabled_fallback_keys.add(adapter_key)
                    attempt_debug["disabled_after_error"] = True
                    logger.error(
                        "disabled fallback extractor after repeated/fatal error",
                        extra={
                            "adapter_key": adapter_key,
                            "failure_count": fail_count,
                        },
                    )
                logger.error(message)
            fallback_attempts.append(attempt_debug)
    unique_filtered = tuple(_unique_preserve_order(collected))
    unique_sources: list[dict[str, str]] = []
    seen_source_keys: set[tuple[str, str]] = set()
    for item in collected_sources:
        key = (item["video_url"], item["extracted_from_url"])
        if key in seen_source_keys:
            continue
        seen_source_keys.add(key)
        unique_sources.append(item)
    return unique_filtered, fallback_attempts, unique_sources


def _should_disable_fallback_adapter(
    *,
    module_path: str,
    error: Exception,
    failure_count: int,
) -> bool:
    if failure_count >= 3:
        return True
    msg = str(error).lower()
    module_lower = module_path.lower()
    webdriver_markers = (
        "webdriver",
        "session not created",
        "chrome not reachable",
        "cannot find chrome binary",
        "stacktrace",
    )
    if "selenium" in module_lower and any(marker in msg for marker in webdriver_markers):
        return True
    return False


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


def _build_daily_video_pairs(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in results:
        game = item.get("game", {})
        date_only = str(game.get("date", ""))[:10]
        home = str(game.get("home", ""))
        away = str(game.get("away", ""))
        key = (date_only, home, away)
        grouped.setdefault(key, []).append(item)

    pairs: list[dict[str, Any]] = []
    for (date_only, home, away), items in grouped.items():
        links: list[str] = []
        link_source_map: dict[str, str] = {}
        source_buckets: dict[str, list[str]] = {}

        for item in items:
            extraction = item.get("extraction", {})
            debug = extraction.get("debug", {}) if isinstance(extraction, dict) else {}
            page_url = str(item.get("page_url", ""))
            for link in extraction.get("found_links", []):
                if not isinstance(link, str):
                    continue
                if link not in links:
                    links.append(link)
            fallback_sources = debug.get("fallback_link_sources", [])
            direct_sources = debug.get("direct_link_sources", [])
            for source_item in [*fallback_sources, *direct_sources]:
                if not isinstance(source_item, dict):
                    continue
                video_url = source_item.get("video_url")
                extracted_from_url = source_item.get("extracted_from_url")
                if not isinstance(video_url, str) or not isinstance(extracted_from_url, str):
                    continue
                link_source_map.setdefault(video_url, extracted_from_url)
            for link in extraction.get("found_links", []):
                if not isinstance(link, str):
                    continue
                extracted_from = link_source_map.get(link, page_url)
                source_buckets.setdefault(extracted_from, [])
                if link not in source_buckets[extracted_from]:
                    source_buckets[extracted_from].append(link)

        selected_source = ""
        selected_links: list[str] = []
        if source_buckets:
            source_candidates = sorted(
                source_buckets.items(),
                key=lambda kv: (
                    0 if "guidedesgemmes.com" in kv[0] else 1,
                    -len(kv[1]),
                    kv[0],
                ),
            )
            for source, bucket_links in source_candidates:
                if len(bucket_links) >= 2:
                    selected_source = source
                    selected_links = bucket_links
                    break
            if not selected_links:
                selected_source, selected_links = source_candidates[0]

        main_video_url = selected_links[0] if len(selected_links) >= 1 else (links[0] if links else "")
        backup_video_url = selected_links[1] if len(selected_links) >= 2 else (links[1] if len(links) >= 2 else "")

        pairs.append(
            {
                "date": date_only,
                "home": home,
                "away": away,
                "source_feed_page": selected_source,
                "main_video_url": main_video_url,
                "backup_video_url": backup_video_url,
                "all_video_urls": links,
            }
        )

    pairs.sort(key=lambda row: (row["date"], row["away"], row["home"]))
    return pairs


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _build_target_page_fetcher(
    *,
    stack: ExitStack,
    config: ScoutConfig,
    options: RunOptions,
    http_fetcher: HttpFetcher,
    logger: logging.Logger,
) -> Any:
    if options.dry_run:
        return http_fetcher
    mode = (config.http.target_page_fetch_mode or "http").strip().lower()
    if mode == "http":
        return http_fetcher
    if mode == "playwright":
        return stack.enter_context(
            PlaywrightFetcher(
                user_agent=config.http.user_agent,
                request_headers=config.http.request_headers,
                headless=config.http.playwright_headless,
                wait_until=config.http.playwright_wait_until,
                timeout_seconds=config.http.playwright_timeout_seconds,
                logger=logger,
            )
        )
    raise ValueError(f"unsupported http.target_page_fetch_mode: {config.http.target_page_fetch_mode}")
