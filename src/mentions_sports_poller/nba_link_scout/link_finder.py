from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

from .models import LinkSearchRule


def extract_links_from_html(html: str, *, base_url: str, rule: LinkSearchRule) -> list[str]:
    parser = _TagAttributeCollector(rule.collect_targets)
    parser.feed(html)
    parser.close()
    normalized = normalize_urls(parser.values, base_url=base_url)
    return apply_link_filters(normalized, base_url=rule.base_url or base_url, rule=rule)


def normalize_urls(raw_urls: list[str], *, base_url: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls:
        value = raw.strip()
        if not value:
            continue
        absolute = urljoin(base_url, value)
        absolute, _fragment = urldefrag(absolute)
        if absolute in seen:
            continue
        seen.add(absolute)
        normalized.append(absolute)
    return normalized


def apply_link_filters(urls: list[str], *, base_url: str, rule: LinkSearchRule) -> list[str]:
    base_domain = urlparse(base_url).netloc.lower()
    allowed_schemes = {scheme.lower() for scheme in rule.constraints.allowed_schemes}
    filtered: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in allowed_schemes:
            continue
        if rule.constraints.require_same_domain and parsed.netloc.lower() != base_domain:
            continue
        if rule.constraints.must_contain and any(
            token not in url for token in rule.constraints.must_contain
        ):
            continue
        if rule.include_patterns and not any(_pattern_match(url, p) for p in rule.include_patterns):
            continue
        if rule.exclude_patterns and any(_pattern_match(url, p) for p in rule.exclude_patterns):
            continue
        filtered.append(url)
    return filtered


def _pattern_match(url: str, pattern: str) -> bool:
    if pattern.startswith("re:"):
        return re.search(pattern[3:], url) is not None
    return pattern in url


class _TagAttributeCollector(HTMLParser):
    def __init__(self, collect_targets: tuple[str, ...]) -> None:
        super().__init__(convert_charrefs=True)
        parsed_targets: set[tuple[str, str]] = set()
        for target in collect_targets:
            if "." not in target:
                continue
            tag, attribute = target.split(".", 1)
            parsed_targets.add((tag.lower(), attribute.lower()))
        self.targets = parsed_targets
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs)

    def _collect(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value for key, value in attrs}
        tag_name = tag.lower()
        for expected_tag, expected_attr in self.targets:
            if expected_tag != tag_name:
                continue
            value = attr_map.get(expected_attr)
            if value:
                self.values.append(value)
