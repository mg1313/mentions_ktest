from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

from .discovery import discover_open_mentions_sports_markets, select_active_tickers
from .orderbook import normalize_orderbook
from .storage import SQLiteStore
from .time_utils import to_utc_iso, utc_now
from .types import DiscoveredMarket
from .vwap import compute_liquidity_metrics


class MentionsSportsPoller:
    def __init__(
        self,
        settings: Any,
        client: Any,
        store: SQLiteStore,
        logger: logging.Logger | None = None,
        sleep_fn: Any | None = None,
        random_fn: Any | None = None,
        monotonic_fn: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.store = store
        self.logger = logger or logging.getLogger(__name__)
        self._sleep = sleep_fn or time.sleep
        self._random = random_fn or random.random
        self._monotonic = monotonic_fn or time.monotonic
        self._last_refresh_monotonic: float | None = None
        self._markets_by_ticker: dict[str, DiscoveredMarket] = {}
        self._active_tickers: set[str] = set()

    def run_forever(self) -> None:
        while True:
            cycle_start = self._monotonic()
            self.poll_once()
            elapsed = self._monotonic() - cycle_start
            jitter = self._random() * max(0, self.settings.poll_jitter_seconds)
            sleep_seconds = max(0.0, self.settings.poll_interval_seconds - elapsed) + jitter
            self._sleep(sleep_seconds)

    def poll_once(self) -> None:
        now = utc_now()
        self._refresh_universe_if_due(now)

        ts_utc = to_utc_iso(now)
        success_count = 0
        error_count = 0
        cycle_start = self._monotonic()
        for ticker in sorted(self._active_tickers):
            market = self._markets_by_ticker.get(ticker)
            if not market:
                continue
            try:
                payload = self.client.get_orderbook(ticker)
                raw_orderbook = payload.get("orderbook", {})
                levels_by_side = normalize_orderbook(
                    orderbook_payload=raw_orderbook,
                    depth_levels_limit=self.settings.depth_levels_limit,
                    depth_target_notional_dollars=self.settings.depth_target_notional_dollars,
                )
                all_levels = []
                for side_levels in levels_by_side.values():
                    all_levels.extend(side_levels)
                metrics = compute_liquidity_metrics(
                    ts_utc=ts_utc,
                    ticker=ticker,
                    levels_by_side=levels_by_side,
                    budgets_dollars=self.settings.vwap_budgets_dollars,
                )
                self.store.persist_market_poll(
                    ts_utc=ts_utc,
                    market=market,
                    raw_orderbook_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
                    levels=all_levels,
                    metrics_row=metrics,
                )
                success_count += 1
            except Exception:
                error_count += 1
                self.logger.exception("market poll failed", extra={"ticker": ticker})

        duration_seconds = self._monotonic() - cycle_start
        self.logger.info(
            "poll cycle complete",
            extra={
                "ts_utc": ts_utc,
                "active_set_size": len(self._active_tickers),
                "markets_ok": success_count,
                "markets_failed": error_count,
                "duration_seconds": duration_seconds,
            },
        )

    def _refresh_universe_if_due(self, now_utc: Any) -> None:
        now_mono = self._monotonic()
        if self._last_refresh_monotonic is not None:
            elapsed = now_mono - self._last_refresh_monotonic
            if elapsed < self.settings.universe_refresh_seconds:
                return

        try:
            markets = discover_open_mentions_sports_markets(self.client, logger=self.logger)
            self.store.upsert_market_meta(markets)
            self._markets_by_ticker = {market.ticker: market for market in markets}
            self._active_tickers = select_active_tickers(
                markets=markets,
                now_utc=now_utc,
                close_within_hours=self.settings.active_close_within_hours,
                pinned_tickers=self.settings.pinned_tickers,
            )
            self._last_refresh_monotonic = now_mono
            self.logger.info(
                "market universe refreshed",
                extra={
                    "markets_discovered": len(markets),
                    "active_set_size": len(self._active_tickers),
                },
            )
        except Exception:
            # Preserve last active set and fail open when refresh has transient issues.
            self.logger.exception("universe refresh failed")
