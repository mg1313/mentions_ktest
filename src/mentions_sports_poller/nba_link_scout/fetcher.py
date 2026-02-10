from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    text: str


class HttpFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        user_agent: str,
        request_headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        logger: logging.Logger | None = None,
        session: Any | None = None,
        sleep_fn: Any | None = None,
        random_fn: Any | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.follow_redirects = follow_redirects
        self.logger = logger or logging.getLogger(__name__)
        default_headers = {"User-Agent": user_agent}
        if request_headers:
            default_headers.update(request_headers)
        self._session = session or httpx.Client(
            headers=default_headers,
            follow_redirects=follow_redirects,
        )
        self._owns_session = session is None
        self._sleep = sleep_fn or time.sleep
        self._random = random_fn or random.random

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "HttpFetcher":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FetchResponse:
        response = self._request_with_retry(url=url, params=params, headers=headers)
        return FetchResponse(url=str(response.url), status_code=response.status_code, text=response.text)

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request_with_retry(url=url, params=params, headers=headers)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("expected top-level JSON object")
        return payload

    def _request_with_retry(
        self,
        *,
        url: str,
        params: dict[str, str] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                retryable = code == 429 or code >= 500
                if not retryable or attempt >= self.max_retries:
                    raise
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt >= self.max_retries:
                    raise

            sleep_seconds = self._backoff_seconds(attempt)
            self.logger.warning(
                "request failed, retrying",
                extra={
                    "url": url,
                    "attempt": attempt + 1,
                    "sleep_seconds": sleep_seconds,
                },
            )
            self._sleep(sleep_seconds)
            attempt += 1

    def _backoff_seconds(self, attempt: int) -> float:
        exp = self.backoff_base_seconds * (2**attempt)
        jitter = self.backoff_base_seconds * self._random()
        return exp + jitter
