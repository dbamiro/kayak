"""Scheduled maintenance orchestrator — entitlements, pending incentives, optional crawl.

Cron (daily 06:00 UTC — required minimum):
  0 6 * * * cd /app/Kayak && PYTHONPATH=. python -m jobs.run_scheduled

With optional jobs:
  PYTHONPATH=. python -m jobs.run_scheduled --expire-pending --crawl
"""

from __future__ import annotations

import argparse

from jobs._common import bootstrap_job_env, exit_from_results
from jobs.tasks import (
    run_daily_crawl_task,
    run_expire_entitlements_task,
    run_expire_pending_incentives_task,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kayak scheduled jobs")
    parser.add_argument("--skip-expire", action="store_true", help="Skip Hunt Pass entitlement expiry")
    parser.add_argument(
        "--expire-pending",
        action="store_true",
        help="Expire stale pending_review incentives",
    )
    parser.add_argument(
        "--pending-stale-days",
        type=int,
        default=None,
        help="Override PENDING_INCENTIVE_TTL_DAYS for --expire-pending",
    )
    parser.add_argument("--crawl", action="store_true", help="Run daily crawl when ENABLE_DAILY_CRAWL=true")
    parser.add_argument("--crawl-mode", choices=["http", "playwright"], default="http")
    parser.add_argument("--crawl-limit", type=int, default=None)
    args = parser.parse_args()

    bootstrap_job_env()
    results = []

    if not args.skip_expire:
        results.append(run_expire_entitlements_task())
    if args.expire_pending:
        results.append(run_expire_pending_incentives_task(stale_days=args.pending_stale_days))
    if args.crawl:
        results.append(
            run_daily_crawl_task(
                mode=args.crawl_mode,
                limit=args.crawl_limit,
                require_enable_flag=True,
            )
        )

    if not results:
        results.append(run_expire_entitlements_task())

    exit_from_results(results)


if __name__ == "__main__":
    main()
