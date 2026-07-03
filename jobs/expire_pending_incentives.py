"""Expire stale pending-review incentives — optional daily cron."""

from __future__ import annotations

import argparse

from jobs._common import bootstrap_job_env, exit_from_results
from jobs.tasks import run_expire_pending_incentives_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Expire stale pending_review incentives")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=None,
        help="Days before pending rows without expires_at are expired (default: PENDING_INCENTIVE_TTL_DAYS env)",
    )
    args = parser.parse_args()
    bootstrap_job_env()
    exit_from_results([run_expire_pending_incentives_task(stale_days=args.stale_days)])


if __name__ == "__main__":
    main()
