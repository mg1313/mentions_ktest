from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from .fetcher import FetchResponse


class PlaywrightFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        request_headers: dict[str, str] | None = None,
        headless: bool = True,
        wait_until: str = "domcontentloaded",
        timeout_seconds: float = 60.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.request_headers = request_headers or {}
        self.headless = headless
        self.wait_until = wait_until
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger(__name__)
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "PlaywrightFetcher":
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright "
                "and python -m playwright install chromium"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            extra_http_headers=self.request_headers,
            locale="en-US",
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FetchResponse:
        if self._context is None:
            raise RuntimeError("PlaywrightFetcher must be used as a context manager")
        if headers:
            # keep deterministic shared-context behavior; per-request headers are not supported here.
            self.logger.debug("ignoring per-request headers for PlaywrightFetcher")

        request_url = _append_query(url, params) if params else url
        page = self._context.new_page()
        try:
            response = page.goto(
                request_url,
                wait_until=self.wait_until,
                timeout=int(self.timeout_seconds * 1000),
            )
            html = page.content()
            final_url = page.url
            status_code = int(response.status) if response is not None else 200
            if status_code >= 400:
                _raise_http_error(status_code=status_code, url=final_url, text=html)
            return FetchResponse(url=final_url, status_code=status_code, text=html)
        finally:
            page.close()


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = parsed.query
    suffix = urlencode(params)
    merged = f"{query}&{suffix}" if query else suffix
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, merged, parsed.fragment))


def _raise_http_error(*, status_code: int, url: str, text: str) -> None:
    request = httpx.Request("GET", url)
    response = httpx.Response(status_code=status_code, text=text, request=request)
    raise httpx.HTTPStatusError(
        f"Client error '{status_code}' for url '{url}'",
        request=request,
        response=response,
    )
