import httpx

from mentions_sports_poller.nba_link_scout.fetcher import HttpFetcher


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.url = "https://example.com/test"
        self.request = httpx.Request("GET", self.url)
        self.text = "{}"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=self.request, response=self)

    def json(self) -> dict:
        return self._payload


class _SequenceSession:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.calls = 0

    def get(self, *_args, **_kwargs):  # noqa: ANN001
        index = min(self.calls, len(self.statuses) - 1)
        self.calls += 1
        return _FakeResponse(self.statuses[index])


def test_fetcher_does_not_retry_non_retryable_403() -> None:
    session = _SequenceSession([403, 200, 200])
    fetcher = HttpFetcher(
        timeout_seconds=1.0,
        max_retries=3,
        backoff_base_seconds=0.01,
        user_agent="test-agent",
        session=session,
        sleep_fn=lambda _seconds: None,
        random_fn=lambda: 0.0,
    )
    try:
        try:
            fetcher.get_text("https://example.com/blocked")
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 403
        else:
            raise AssertionError("expected HTTPStatusError for 403")
        assert session.calls == 1
    finally:
        fetcher.close()
