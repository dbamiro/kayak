"""Scheduled background job tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.services.entitlement_service import EntitlementService
from app.services.incentive_expiry_service import IncentiveExpiryService
from app.services.incentive_service import create_incentive, merge_parsed_into_data
from app.services.incentive_text_parser import parse_incentive_text
from jobs._common import JobStatus, bootstrap_job_env, exit_from_results, log_job_result
from jobs.tasks import (
    run_daily_crawl_task,
    run_expire_entitlements_task,
    run_expire_pending_incentives_task,
)


@pytest.mark.db
def test_expire_entitlements_task_marks_expired(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, name) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id
            """,
            (f"job-exp-{uuid4().hex[:8]}@example.com", "Job"),
        )
        uid = UUID(str(cur.fetchone()[0]))
        cur.execute(
            """
            INSERT INTO customer_entitlements (
                user_id, plan_code, starts_at, expires_at, status, source
            ) VALUES (%s, 'hunt_pass_30', now() - interval '31 days', now() - interval '1 day', 'active', 'test')
            """,
            (str(uid),),
        )
    conn.commit()
    result = run_expire_entitlements_task()
    assert result.status == JobStatus.OK
    assert result.count >= 1
    assert EntitlementService.has_active_hunt_pass(conn, uid) is False


@pytest.mark.db
def test_expire_pending_incentives_by_expires_at(conn):
    bid = UUID("b0000000-0000-4000-8000-000000000001")
    parsed = parse_incentive_text("1 month free")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    data = merge_parsed_into_data(
        {
            "building_id": bid,
            "listed_rent": 2000,
            "lease_term_months": 12,
            "raw_text": "1 month free",
            "status": "pending_review",
            "is_demo": False,
            "capture_method": "user_submission",
            "incentive_type": "free_months",
            "expires_at": past,
        },
        parsed,
    )
    row = create_incentive(conn, data)
    iid = UUID(str(row["id"]))
    n = IncentiveExpiryService.expire_pending_incentives(conn, stale_days=90)
    assert n >= 1
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM incentives WHERE id = %s", (str(iid),))
        assert cur.fetchone()[0] == "expired"


@pytest.mark.db
def test_expire_pending_incentives_by_stale_days(conn):
    bid = UUID("b0000000-0000-4000-8000-000000000001")
    parsed = parse_incentive_text("2 months free")
    data = merge_parsed_into_data(
        {
            "building_id": bid,
            "listed_rent": 2100,
            "lease_term_months": 14,
            "raw_text": "2 months free",
            "status": "pending_review",
            "is_demo": False,
            "capture_method": "crawler",
            "incentive_type": "free_months",
        },
        parsed,
    )
    row = create_incentive(conn, data)
    iid = UUID(str(row["id"]))
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE incentives SET created_at = now() - interval '100 days' WHERE id = %s",
            (str(iid),),
        )
    conn.commit()
    n = IncentiveExpiryService.expire_pending_incentives(conn, stale_days=90)
    assert n >= 1
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM incentives WHERE id = %s", (str(iid),))
        assert cur.fetchone()[0] == "expired"


@pytest.mark.db
def test_verified_incentive_not_expired_by_pending_job(conn):
    bid = UUID("b0000000-0000-4000-8000-000000000001")
    parsed = parse_incentive_text("2 months free")
    past = datetime.now(timezone.utc) - timedelta(days=100)
    data = merge_parsed_into_data(
        {
            "building_id": bid,
            "listed_rent": 2200,
            "lease_term_months": 12,
            "raw_text": "2 months free",
            "status": "verified",
            "is_demo": False,
            "capture_method": "manual_admin",
            "incentive_type": "free_months",
        },
        parsed,
    )
    row = create_incentive(conn, data)
    iid = UUID(str(row["id"]))
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE incentives SET created_at = %s WHERE id = %s",
            (past, str(iid)),
        )
    conn.commit()
    IncentiveExpiryService.expire_pending_incentives(conn, stale_days=90)
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM incentives WHERE id = %s", (str(iid),))
        assert cur.fetchone()[0] == "verified"


def test_daily_crawl_skipped_without_enable_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENABLE_DAILY_CRAWL", raising=False)
    bootstrap_job_env()
    result = run_daily_crawl_task(require_enable_flag=True)
    assert result.status == JobStatus.SKIPPED


def test_exit_from_results_raises_on_failure():
    from jobs._common import JobResult

    with pytest.raises(SystemExit) as exc:
        exit_from_results([JobResult("x", JobStatus.FAILED, 0, "boom")])
    assert exc.value.code == 1


def test_exit_from_results_ok():
    from jobs._common import JobResult

    with pytest.raises(SystemExit) as exc:
        exit_from_results([JobResult("x", JobStatus.OK, 1, "ok")])
    assert exc.value.code == 0


def test_log_job_result_does_not_raise(caplog: pytest.LogCaptureFixture):
    import logging

    from jobs._common import JobResult

    bootstrap_job_env()
    with caplog.at_level(logging.INFO, logger="kayak.jobs"):
        log_job_result(JobResult("test", JobStatus.OK, 0, "fine"))
    assert "job=test" in caplog.text
