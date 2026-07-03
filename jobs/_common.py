"""Shared helpers for CLI/cron jobs (no FastAPI required)."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class JobStatus(str, Enum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class JobResult:
    name: str
    status: JobStatus
    count: int = 0
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status != JobStatus.FAILED


def bootstrap_job_env(*, log_level: int = logging.INFO) -> None:
    """Load .env and configure logging for cron/CLI runs."""
    load_dotenv()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def env_flag(name: str) -> bool:
    return os.getenv(name, "").lower() in ("1", "true", "yes")


def log_job_result(result: JobResult) -> None:
    log = logging.getLogger("kayak.jobs")
    msg = f"job={result.name} status={result.status.value} count={result.count} {result.detail}".strip()
    if result.status == JobStatus.FAILED:
        log.error(msg)
    elif result.status == JobStatus.SKIPPED:
        log.info(msg)
    else:
        log.info(msg)


def exit_from_results(results: list[JobResult]) -> None:
    for r in results:
        log_job_result(r)
    if any(r.status == JobStatus.FAILED for r in results):
        raise SystemExit(1)
    raise SystemExit(0)
