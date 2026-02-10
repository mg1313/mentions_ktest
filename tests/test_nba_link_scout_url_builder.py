from mentions_sports_poller.nba_link_scout.models import Game, LinkSearchRule, TargetSiteRule
from mentions_sports_poller.nba_link_scout.url_builder import build_urls_for_game


def test_build_urls_for_game_from_template() -> None:
    game = Game(
        date="2026-02-10",
        home="Golden State Warriors",
        away="San Antonio Spurs",
        game_id="0022600001",
    )
    site_rule = TargetSiteRule(
        name="example-site",
        domain="example.com",
        url_templates=("https://example.com/{date_only}/{away_slug}-at-{home_slug}/{game_id}",),
        required_params=("game_id", "date_only"),
        link_search_rule=LinkSearchRule(base_url=None),
    )

    candidates, errors = build_urls_for_game(game, (site_rule,))
    assert errors == []
    assert len(candidates) == 1
    assert (
        candidates[0].page_url
        == "https://example.com/2026-02-10/san-antonio-spurs-at-golden-state-warriors/0022600001"
    )


def test_build_urls_supports_month_name_and_unpadded_day() -> None:
    game = Game(
        date="2026-02-09",
        home="Portland Trail Blazers",
        away="Philadelphia 76ers",
        game_id="G2",
    )
    site_rule = TargetSiteRule(
        name="basketball-video",
        domain="basketball-video.com",
        url_templates=(
            "https://basketball-video.com/{away_slug}-vs-{home_slug}-full-game-replay-"
            "{month_name_lower}-{day_unpadded}-{year}-nba",
        ),
        required_params=("month_name_lower", "day_unpadded", "year"),
        link_search_rule=LinkSearchRule(base_url=None),
    )

    candidates, errors = build_urls_for_game(game, (site_rule,))
    assert errors == []
    assert candidates[0].page_url == (
        "https://basketball-video.com/philadelphia-76ers-vs-portland-trail-blazers-"
        "full-game-replay-february-9-2026-nba"
    )
