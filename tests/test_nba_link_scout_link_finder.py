from pathlib import Path

from mentions_sports_poller.nba_link_scout.link_finder import apply_link_filters, extract_links_from_html
from mentions_sports_poller.nba_link_scout.models import LinkConstraints, LinkSearchRule


def test_extract_links_from_html_and_normalize_with_fixture() -> None:
    html = Path("tests/fixtures/scout_sample_page.html").read_text(encoding="utf-8")
    rule = LinkSearchRule(
        base_url=None,
        include_patterns=("/watch/",),
        exclude_patterns=("styles.css",),
        collect_targets=("a.href", "source.src", "iframe.src", "link.href"),
        constraints=LinkConstraints(require_same_domain=True, must_contain=("/watch/",)),
    )

    links = extract_links_from_html(
        html,
        base_url="https://example.com/games/0022600001",
        rule=rule,
    )
    assert links == [
        "https://example.com/watch/highlight-a",
        "https://example.com/watch/highlight-b",
        "https://example.com/watch/stream-a.m3u8",
    ]


def test_apply_link_filters_include_exclude_regex() -> None:
    urls = [
        "https://example.com/watch/alpha",
        "https://example.com/watch/beta",
        "https://example.com/watch/gamma-test",
    ]
    rule = LinkSearchRule(
        base_url="https://example.com/base",
        include_patterns=("re:/watch/(alpha|gamma)",),
        exclude_patterns=("gamma",),
        constraints=LinkConstraints(require_same_domain=True),
    )
    filtered = apply_link_filters(urls, base_url="https://example.com/base", rule=rule)
    assert filtered == ["https://example.com/watch/alpha"]
