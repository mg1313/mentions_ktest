from __future__ import annotations

import argparse
import logging

from .config import Settings
from .kalshi_client import KalshiClient
from .poller import MentionsSportsPoller
from .storage import SQLiteStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi Mentions Sports orderbook poller")
    parser.add_argument("--once", action="store_true", help="Run a single poll cycle and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger("mentions_sports_poller")

    settings = Settings.from_env()
    store = SQLiteStore(settings.db_path)
    store.create_schema()

    with KalshiClient(
        api_base_url=settings.api_base_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        backoff_base_seconds=settings.backoff_base_seconds,
        rate_limit_per_second=settings.rate_limit_per_second,
        logger=logger,
    ) as client:
        poller = MentionsSportsPoller(
            settings=settings,
            client=client,
            store=store,
            logger=logger,
        )
        if args.once:
            poller.poll_once()
            return
        poller.run_forever()


if __name__ == "__main__":
    main()
