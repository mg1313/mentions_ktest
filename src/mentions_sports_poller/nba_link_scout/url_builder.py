from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .models import Game, LinkSearchRule, TargetSiteRule, UrlCandidate


def build_urls_for_game(
    game: Game,
    target_sites: tuple[TargetSiteRule, ...],
    *,
    logger: logging.Logger | None = None,
) -> tuple[list[UrlCandidate], list[str]]:
    log = logger or logging.getLogger(__name__)
    context = _build_context(game)
    candidates: list[UrlCandidate] = []
    errors: list[str] = []

    for site in target_sites:
        missing = [field for field in site.required_params if not context.get(field)]
        if missing:
            message = f"target '{site.name}' missing required params: {','.join(missing)}"
            errors.append(message)
            log.warning(message, extra={"game_id": game.game_id})
            continue

        templates = site.url_templates or ()
        for template in templates:
            try:
                page_url = template.format_map(context)
            except KeyError as exc:
                missing_key = str(exc).strip("'")
                message = (
                    f"target '{site.name}' template uses missing key '{missing_key}' for game {game.game_id}"
                )
                errors.append(message)
                log.warning(message)
                continue
            candidates.append(
                UrlCandidate(
                    game=game,
                    target_site_name=site.name,
                    page_url=page_url,
                    link_search_rule=_resolve_link_rule(site.link_search_rule, context),
                )
            )

        if not templates and site.link_search_rule.base_url:
            base_url = site.link_search_rule.base_url.format_map(context)
            candidates.append(
                UrlCandidate(
                    game=game,
                    target_site_name=site.name,
                    page_url=base_url,
                    link_search_rule=_resolve_link_rule(site.link_search_rule, context),
                )
            )

    return candidates, errors


def _build_context(game: Game) -> dict[str, Any]:
    date_only = game.date[:10]
    year = ""
    month = ""
    day = ""
    day_unpadded = ""
    month_name = ""
    month_name_lower = ""
    month_name_short = ""
    month_name_short_lower = ""
    try:
        parsed = datetime.fromisoformat(date_only)
        year = f"{parsed.year:04d}"
        month = f"{parsed.month:02d}"
        day = f"{parsed.day:02d}"
        day_unpadded = str(parsed.day)
        month_name = parsed.strftime("%B")
        month_name_lower = month_name.lower()
        month_name_short = parsed.strftime("%b")
        month_name_short_lower = month_name_short.lower()
    except ValueError:
        pass
    return {
        "game_id": game.game_id,
        "date": game.date,
        "date_only": date_only,
        "year": year,
        "month": month,
        "day": day,
        "day_unpadded": day_unpadded,
        "month_name": month_name,
        "month_name_lower": month_name_lower,
        "month_name_short": month_name_short,
        "month_name_short_lower": month_name_short_lower,
        "home": game.home,
        "away": game.away,
        "home_slug": _slugify(game.home),
        "away_slug": _slugify(game.away),
        "matchup_slug": f"{_slugify(game.away)}-vs-{_slugify(game.home)}",
    }


def _slugify(value: str) -> str:
    keep = [char.lower() if char.isalnum() else "-" for char in value.strip()]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _resolve_link_rule(rule: LinkSearchRule, context: dict[str, Any]) -> LinkSearchRule:
    base_url = rule.base_url.format_map(context) if rule.base_url else None
    return LinkSearchRule(
        base_url=base_url,
        include_patterns=rule.include_patterns,
        exclude_patterns=rule.exclude_patterns,
        collect_targets=rule.collect_targets,
        constraints=rule.constraints,
    )
