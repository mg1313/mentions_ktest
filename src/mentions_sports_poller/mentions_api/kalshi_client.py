from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx


class KalshiClient:
    def __init__(
        self,
        api_base_url: str,
        request_timeout_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        rate_limit_per_second: int,
        logger: logging.Logger | None = None,
        session: Any | None = None,
        sleep_fn: Any | None = None,
        random_fn: Any | None = None,
        monotonic_fn: Any | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.rate_limit_per_second = max(1, rate_limit_per_second)
        self.logger = logger or logging.getLogger(__name__)
        self._session = session or httpx.Client(timeout=request_timeout_seconds)
        self._owns_session = session is None
        self._sleep = sleep_fn or time.sleep
        self._random = random_fn or random.random
        self._monotonic = monotonic_fn or time.monotonic
        self._min_interval = 1.0 / float(self.rate_limit_per_second)
        self._next_request_ts = 0.0

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "KalshiClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def list_mentions_sports_series(self) -> list[dict[str, Any]]:
        return self._paginate(
            path="/series",
            items_key="series",
            params={"category": "Mentions", "tags": "Sports", "limit": 200},
        )

    def list_open_markets(self, series_ticker: str) -> list[dict[str, Any]]:
        return self._paginate(
            path="/markets",
            items_key="markets",
            params={"series_ticker": series_ticker, "status": "open", "limit": 200},
        )

    def get_orderbook(self, ticker: str) -> dict[str, Any]:
        return self._request_json(f"/markets/{ticker}/orderbook")

    def _paginate(
        self,
        path: str,
        items_key: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        cursor: str | None = None
        all_items: list[dict[str, Any]] = []
        while True:
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor
            payload = self._request_json(path, page_params)
            items = payload.get(items_key, [])
            if not isinstance(items, list):
                raise ValueError(f"Expected list in payload key '{items_key}'")
            all_items.extend(items)
            cursor = payload.get("cursor")
            if not cursor:
                break
        return all_items

    def _throttle(self) -> None:
        now_ts = self._monotonic()
        if now_ts < self._next_request_ts:
            self._sleep(self._next_request_ts - now_ts)
            now_ts = self._monotonic()
        self._next_request_ts = now_ts + self._min_interval

    def _request_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.api_base_url}/{path.lstrip('/')}"
        attempt = 0
        while True:
            self._throttle()
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self.request_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected object JSON payload")
                return payload
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                should_retry = code == 429 or code >= 500
                if not should_retry or attempt >= self.max_retries:
                    raise
            except (httpx.TransportError, httpx.TimeoutException, ValueError):
                if attempt >= self.max_retries:
                    raise

            backoff = self.backoff_base_seconds * (2 ** attempt)
            jitter = self.backoff_base_seconds * self._random()
            sleep_seconds = backoff + jitter
            self.logger.warning(
                "kalshi request failed, retrying",
                extra={"path": path, "attempt": attempt + 1, "sleep_seconds": sleep_seconds},
            )
            self._sleep(sleep_seconds)
            attempt += 1
