"""CLI / scheduled daily crawl."""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

from app.db import get_pool  # noqa: E402
from crawler.fetcher import FetchMode  # noqa: E402
from crawler.run import run_building_crawl  # noqa: E402


def crawl_once(mode: FetchMode, limit: int | None) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        stats = run_building_crawl(conn, default_fetch_mode=mode, building_limit=limit)
    print(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily DMV crawl runner")
    parser.add_argument(
        "--mode",
        choices=["http", "playwright"],
        default="http",
        help="Fetch stack: fast HTTP client vs JS-rendered Playwright",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max buildings per run (debug)")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run APScheduler daily at 06:15 local time (requires process kept alive)",
    )
    args = parser.parse_args()

    mode = FetchMode(args.mode)

    if args.schedule:

        def job() -> None:
            crawl_once(mode, args.limit)

        scheduler = BlockingScheduler()
        scheduler.add_job(job, CronTrigger(hour=6, minute=15))
        scheduler.start()
        return

    crawl_once(mode, args.limit)


if __name__ == "__main__":
    main()
