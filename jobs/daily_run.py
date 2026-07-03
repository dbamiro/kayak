"""CLI / scheduled daily crawl — runs without web server."""

from __future__ import annotations

import argparse
import json

from jobs._common import JobStatus, bootstrap_job_env, exit_from_results
from jobs.tasks import run_daily_crawl_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily DMV crawl runner")
    parser.add_argument(
        "--mode",
        choices=["http", "playwright"],
        default="http",
        help="Default fetch mode when source has no crawl_strategy",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max sources per run")
    parser.add_argument(
        "--source-id",
        type=str,
        default=None,
        help="Crawl a single sources.id (pilot — bypasses ENABLE_DAILY_CRAWL gate)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when ENABLE_DAILY_CRAWL is false (manual ops only)",
    )
    args = parser.parse_args()

    bootstrap_job_env()
    result = run_daily_crawl_task(
        mode=args.mode,
        limit=args.limit,
        source_id=args.source_id,
        require_enable_flag=not args.force and not args.source_id,
    )
    if result.status == JobStatus.OK and result.extra:
        print(json.dumps(result.extra, indent=2, default=str))
    exit_from_results([result])


if __name__ == "__main__":
    main()
