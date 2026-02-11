from mentions_sports_poller.nba_link_scout.runner import _build_daily_video_pairs


def test_build_daily_video_pairs_prefers_two_links_from_same_guidedes_page() -> None:
    results = [
        {
            "game": {"date": "2026-02-09T00:00:00Z", "home": "Portland Trail Blazers", "away": "Philadelphia 76ers"},
            "target_site": "basketball-video",
            "page_url": "https://basketball-video.com/philadelphia-76ers-vs-portland-trail-blazers-full-game-replay-february-9-2026-nba",
            "extraction": {
                "method_used": "fallback",
                "found_links": [
                    "https://ok.ru/video/11932418771628",
                    "https://ok.ru/video/11935217552044",
                    "https://ok.ru/video/11111111111111",
                ],
                "debug": {
                    "fallback_link_sources": [
                        {
                            "video_url": "https://ok.ru/video/11932418771628",
                            "extracted_from_url": "https://guidedesgemmes.com/la-signification-des-bracelets-de-chakra",
                        },
                        {
                            "video_url": "https://ok.ru/video/11935217552044",
                            "extracted_from_url": "https://guidedesgemmes.com/la-signification-des-bracelets-de-chakra",
                        },
                        {
                            "video_url": "https://ok.ru/video/11111111111111",
                            "extracted_from_url": "https://another.example.com/path",
                        },
                    ]
                },
            },
        }
    ]

    pairs = _build_daily_video_pairs(results)
    assert len(pairs) == 1
    row = pairs[0]
    assert row["source_feed_page"] == "https://guidedesgemmes.com/la-signification-des-bracelets-de-chakra"
    assert row["main_video_url"] == "https://ok.ru/video/11932418771628"
    assert row["backup_video_url"] == "https://ok.ru/video/11935217552044"
