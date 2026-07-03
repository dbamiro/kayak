"""Mark expired Hunt Pass / subscription rows — run daily via cron."""

from __future__ import annotations

from jobs._common import bootstrap_job_env, exit_from_results
from jobs.tasks import run_expire_entitlements_task


def main() -> None:
    bootstrap_job_env()
    exit_from_results([run_expire_entitlements_task()])


if __name__ == "__main__":
    main()
