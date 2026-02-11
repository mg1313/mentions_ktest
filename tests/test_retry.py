import httpx

from mentions_sports_poller.mentions_api.kalshi_client import KalshiClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FlakySession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url, params=None, timeout=None):  # noqa: ANN001
        self.calls += 1
        if self.calls < 3:
            raise httpx.ReadTimeout("timeout")
        return FakeResponse({"series": []})


def test_retry_transient_errors_then_succeeds() -> None:
    sleeper_calls: list[float] = []
    session = FlakySession()
    client = KalshiClient(
        api_base_url="https://api.elections.kalshi.com/trade-api/v2",
        request_timeout_seconds=1.0,
        max_retries=4,
        backoff_base_seconds=0.01,
        rate_limit_per_second=1000,
        session=session,
        sleep_fn=lambda seconds: sleeper_calls.append(seconds),
        random_fn=lambda: 0.0,
        monotonic_fn=lambda: 0.0,
    )

    result = client.list_mentions_sports_series()
    assert result == []
    assert session.calls == 3
    assert len(sleeper_calls) >= 2
