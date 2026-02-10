from contextlib import ExitStack
from datetime import date

from mentions_sports_poller.nba_link_scout.fetcher import HttpFetcher
from mentions_sports_poller.nba_link_scout.models import (
    HttpSettings,
    RunOptions,
    ScheduleFieldMap,
    ScheduleSourceConfig,
    ScoutConfig,
)
from mentions_sports_poller.nba_link_scout.runner import _build_target_page_fetcher


def _minimal_config(http: HttpSettings) -> ScoutConfig:
    return ScoutConfig(
        schedule_source=ScheduleSourceConfig(
            provider="file_json",
            file_path="dummy.json",
            field_map=ScheduleFieldMap(game_id="id", date="date", home="home", away="away"),
        ),
        target_sites=(),
        http=http,
    )


def test_target_fetch_mode_http_returns_http_fetcher() -> None:
    config = _minimal_config(HttpSettings(target_page_fetch_mode="http"))
    options = RunOptions(requested_date=date(2026, 2, 10), dry_run=False)
    with ExitStack() as stack:
        http_fetcher = stack.enter_context(
            HttpFetcher(
                timeout_seconds=1.0,
                max_retries=0,
                backoff_base_seconds=0.01,
                user_agent="test-agent",
            )
        )
        target = _build_target_page_fetcher(
            stack=stack,
            config=config,
            options=options,
            http_fetcher=http_fetcher,
            logger=_SilentLogger(),
        )
        assert target is http_fetcher


def test_target_fetch_mode_playwright_uses_playwright_fetcher(monkeypatch) -> None:
    created = {"count": 0}

    class FakePlaywrightFetcher:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            created["count"] += 1
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

    monkeypatch.setattr(
        "mentions_sports_poller.nba_link_scout.runner.PlaywrightFetcher",
        FakePlaywrightFetcher,
    )

    config = _minimal_config(
        HttpSettings(
            target_page_fetch_mode="playwright",
            playwright_headless=True,
            playwright_wait_until="domcontentloaded",
            playwright_timeout_seconds=30.0,
        )
    )
    options = RunOptions(requested_date=date(2026, 2, 10), dry_run=False)
    with ExitStack() as stack:
        http_fetcher = stack.enter_context(
            HttpFetcher(
                timeout_seconds=1.0,
                max_retries=0,
                backoff_base_seconds=0.01,
                user_agent="test-agent",
            )
        )
        target = _build_target_page_fetcher(
            stack=stack,
            config=config,
            options=options,
            http_fetcher=http_fetcher,
            logger=_SilentLogger(),
        )
        assert created["count"] == 1
        assert isinstance(target, FakePlaywrightFetcher)


class _SilentLogger:
    def debug(self, *_args, **_kwargs):  # noqa: ANN001
        return None
