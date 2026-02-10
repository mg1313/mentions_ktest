from pathlib import Path

from mentions_sports_poller.nba_link_scout.models import Game, LinkConstraints, LinkSearchRule, UrlCandidate
from mentions_sports_poller.nba_link_scout.runner import _process_candidate


class StubFetcher:
    def get_text(self, url: str):  # noqa: ANN001
        class Response:
            def __init__(self, response_url: str) -> None:
                self.status_code = 200
                self.text = (
                    "<html><body>"
                    "<a href='/not-a-match'>x</a>"
                    "<a href='https://guidedesgemmes.com/post-1'>hop</a>"
                    "</body></html>"
                )
                self.url = response_url

        return Response(url)


class StubFallback:
    def __init__(self) -> None:
        self.called = 0

    def extract(self, *, page_url: str, html: str) -> list[str]:
        self.called += 1
        return [
            "https://example.com/watch/fallback-a",
            "https://example.com/other/skip",
        ]


def test_process_candidate_invokes_fallback_when_html_has_zero_matches() -> None:
    game = Game(date="2026-02-10", home="A", away="B", game_id="G1")
    candidate = UrlCandidate(
        game=game,
        target_site_name="test-site",
        page_url="https://example.com/page",
        link_search_rule=LinkSearchRule(
            base_url="https://example.com/page",
            include_patterns=("/watch/",),
            constraints=LinkConstraints(require_same_domain=True),
        ),
    )
    fallback = StubFallback()
    result = _process_candidate(
        candidate=candidate,
        fetcher=StubFetcher(),  # type: ignore[arg-type]
        fallback_adapters=[fallback],  # type: ignore[list-item]
        video_link_rule=None,
        logger=_SilentLogger(),
    )
    assert fallback.called >= 1
    assert result.method_used == "fallback"
    assert list(result.found_links) == ["https://example.com/watch/fallback-a"]


def test_process_candidate_runs_fallback_on_intermediate_link_for_okru() -> None:
    game = Game(date="2026-02-10", home="A", away="B", game_id="G1")
    candidate = UrlCandidate(
        game=game,
        target_site_name="basketball-video",
        page_url="https://basketball-video.com/a-vs-b-full-game-replay-february-10-2026-nba",
        link_search_rule=LinkSearchRule(
            base_url="https://basketball-video.com",
            include_patterns=("https://guidedesgemmes.com/",),
            constraints=LinkConstraints(require_same_domain=False),
        ),
    )

    class HopFallback:
        def extract(self, *, page_url: str, html: str) -> list[str]:
            if page_url.startswith("https://guidedesgemmes.com/"):
                return ["https://ok.ru/video/123456789"]
            return []

    result = _process_candidate(
        candidate=candidate,
        fetcher=StubFetcher(),  # type: ignore[arg-type]
        fallback_adapters=[HopFallback()],  # type: ignore[list-item]
        video_link_rule=LinkSearchRule(
            base_url="https://ok.ru",
            include_patterns=("https://ok.ru/video/",),
            constraints=LinkConstraints(require_same_domain=False),
        ),
        logger=_SilentLogger(),
    )
    assert result.method_used == "fallback"
    assert list(result.found_links) == ["https://ok.ru/video/123456789"]


def test_dynamic_fallback_module_adapter() -> None:
    module_path = Path("tests/fixtures/_fallback_mod.py")
    try:
        module_path.write_text(
            "def extract_links(page_url):\n"
            "    return [page_url + '/watch/a', page_url + '/watch/b']\n",
            encoding="utf-8",
        )
        from mentions_sports_poller.nba_link_scout.fallback import FallbackExtractorAdapter
        from mentions_sports_poller.nba_link_scout.models import FallbackExtractorConfig

        adapter = FallbackExtractorAdapter(
            config=FallbackExtractorConfig(
                module_path=str(module_path),
                function_name="extract_links",
            )
        )
        links = adapter.extract(page_url="https://example.com/base", html="<html></html>")
        assert links == ["https://example.com/base/watch/a", "https://example.com/base/watch/b"]
    finally:
        if module_path.exists():
            module_path.unlink()


class _SilentLogger:
    def error(self, *_args, **_kwargs):  # noqa: ANN001
        return None
