"""Job task implementations — DB only, no web server."""

from __future__ import annotations

import logging
from typing import Any

from app.db import close_pool, get_pool
from app.services.entitlement_service import EntitlementService
from app.services.incentive_expiry_service import IncentiveExpiryService
from crawler.fetcher import FetchMode
from crawler.run import run_building_crawl
from jobs._common import JobResult, JobStatus, env_flag

logger = logging.getLogger("kayak.jobs")


def run_expire_entitlements_task() -> JobResult:
    name = "expire_entitlements"
    try:
        pool = get_pool()
        with pool.connection() as conn:
            n = EntitlementService.expire_old_entitlements(conn)
            conn.commit()
        return JobResult(name, JobStatus.OK, n, f"expired_entitlements={n}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("expire_entitlements_failed")
        return JobResult(name, JobStatus.FAILED, 0, str(exc))
    finally:
        close_pool()


def run_expire_pending_incentives_task(*, stale_days: int | None = None) -> JobResult:
    name = "expire_pending_incentives"
    try:
        from app.config import get_settings

        days = stale_days if stale_days is not None else get_settings().pending_incentive_ttl_days
        pool = get_pool()
        with pool.connection() as conn:
            n = IncentiveExpiryService.expire_pending_incentives(conn, stale_days=days)
        return JobResult(name, JobStatus.OK, n, f"expired_pending_incentives={n}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("expire_pending_incentives_failed")
        return JobResult(name, JobStatus.FAILED, 0, str(exc))
    finally:
        close_pool()


def run_daily_crawl_task(
    *,
    mode: str = "http",
    limit: int | None = None,
    source_id: str | None = None,
    require_enable_flag: bool = True,
) -> JobResult:
    name = "daily_crawl"
    if require_enable_flag and not env_flag("ENABLE_DAILY_CRAWL"):
        return JobResult(
            name,
            JobStatus.SKIPPED,
            0,
            "ENABLE_DAILY_CRAWL not set — crawl disabled",
        )
    try:
        from uuid import UUID

        pool = get_pool()
        with pool.connection() as conn:
            stats: dict[str, Any] = run_building_crawl(
                conn,
                default_fetch_mode=FetchMode(mode),
                building_limit=limit,
                source_id=UUID(source_id) if source_id else None,
            )
        processed = int(stats.get("sources_processed") or 0)
        status = str(stats.get("status") or "ok")
        return JobResult(
            name,
            JobStatus.OK,
            processed,
            f"sources_processed={processed} crawl_status={status}",
            extra=stats,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("daily_crawl_failed")
        return JobResult(name, JobStatus.FAILED, 0, str(exc))
    finally:
        close_pool()
