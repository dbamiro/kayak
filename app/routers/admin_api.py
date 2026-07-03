"""Admin-only operational endpoints (sources, crawls, placeholder health)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from psycopg.rows import dict_row

from app.deps import ConnDep
from app.deps_auth import AdminUser
from app.rate_limit import check_admin_api_limit
from app.schemas import (
    AdminIncentiveCreate,
    AdminIncentiveImportResult,
    AdminIncentiveImportRowError,
    AdminIncentiveRejectBody,
    AdminIncentiveUpdate,
    IncentiveCardOut,
)
from app.services.incentive_csv_import import validate_and_import_csv
from app.services.incentive_review_service import (
    list_incentives_for_admin,
    reject_incentive,
    update_incentive_for_review,
    verify_incentive,
)
from app.services.incentive_service import create_incentive, merge_parsed_into_data, resolve_building_id
from app.services.incentive_text_parser import parse_incentive_text
from crawler.block_detection import source_status_bucket

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(check_admin_api_limit)],
)


@router.post("/incentives", response_model=IncentiveCardOut, status_code=201)
def admin_create_incentive(
    conn: ConnDep,
    body: AdminIncentiveCreate,
    admin: AdminUser,
) -> IncentiveCardOut:
    """Enter a verified real incentive (not demo). Parses raw_text and stores snapshot."""
    parsed = parse_incentive_text(body.raw_text)
    building_id = body.building_id
    if not building_id and body.building_name:
        building_id = resolve_building_id(
            conn, building_name=body.building_name, city=body.city
        )
    if not building_id:
        raise HTTPException(
            400,
            "building_id or an existing building_name+city is required",
        )

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    data = merge_parsed_into_data(
        {
            "building_id": building_id,
            "source_url": body.source_url,
            "listed_rent": body.listed_rent,
            "lease_term_months": body.lease_term_months,
            "free_months": body.free_months,
            "waived_fee_amount": body.waived_fee_amount or 0,
            "gift_card_amount": body.gift_card_amount or 0,
            "custom_credit_amount": body.custom_credit_amount or 0,
            "recurring_fee_monthly": body.recurring_fee_monthly or 0,
            "raw_text": body.raw_text,
            "applies_to": body.applies_to,
            "expires_at": body.expires_at,
            "verification_method": body.verification_method or "leasing_office_verified",
            "capture_method": "manual_admin",
            "confidence_score": max(parsed.confidence_score, 0.85),
            "is_demo": False,
            "status": "verified",
            "verified_at": now,
            "reviewed_at": now,
            "reviewed_by_user_id": admin.id,
            "metadata": {"city": body.city, "neighborhood": body.neighborhood},
        },
        parsed,
    )
    if not data.get("incentive_type") or data["incentive_type"] == "unknown":
        data["incentive_type"] = parsed.incentive_type

    row = create_incentive(conn, data)
    return IncentiveCardOut.model_validate(row)


@router.post("/incentives/import", response_model=AdminIncentiveImportResult)
async def admin_import_incentives_csv(
    conn: ConnDep,
    admin: AdminUser,
    file: UploadFile,
    dry_run: bool = Query(False, description="Validate CSV without inserting rows"),
) -> AdminIncentiveImportResult:
    """Bulk import admin-verified incentives from CSV. See fixtures/incentives_import_template.csv and docs/DMV_INCENTIVE_IMPORT.md."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")
    raw = await file.read()
    if not raw.strip():
        raise HTTPException(400, "CSV file is empty")
    if len(raw) > 2_000_000:
        raise HTTPException(400, "CSV file too large (max 2MB)")

    outcome = validate_and_import_csv(
        conn,
        raw,
        admin_user_id=admin.id,
        dry_run=dry_run,
    )
    return AdminIncentiveImportResult(
        dry_run=outcome.dry_run,
        created_count=outcome.created_count,
        error_count=outcome.error_count,
        errors=[
            AdminIncentiveImportRowError(row=e.row, field=e.field, message=e.message)
            for e in outcome.errors
        ],
        created_incentive_ids=outcome.created_incentive_ids,
    )


@router.get("/incentives", response_model=list[IncentiveCardOut])
def admin_list_incentives(
    conn: ConnDep,
    _admin: AdminUser,
    status: str | None = Query(None, description="pending_review, verified, rejected, expired, active"),
    capture_method: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> list[IncentiveCardOut]:
    rows = list_incentives_for_admin(
        conn, status=status, capture_method=capture_method, limit=limit
    )
    return [IncentiveCardOut.model_validate(r) for r in rows]


@router.get("/incentives/{incentive_id}", response_model=IncentiveCardOut)
def admin_get_incentive(
    conn: ConnDep,
    incentive_id: UUID,
    _admin: AdminUser,
) -> IncentiveCardOut:
    from app.services.incentive_service import get_incentive

    row = get_incentive(conn, incentive_id)
    if not row:
        raise HTTPException(404, "incentive_not_found")
    return IncentiveCardOut.model_validate(row)


@router.patch("/incentives/{incentive_id}", response_model=IncentiveCardOut)
def admin_update_incentive(
    conn: ConnDep,
    incentive_id: UUID,
    body: AdminIncentiveUpdate,
    _admin: AdminUser,
) -> IncentiveCardOut:
    """Edit parsed fields before verifying."""
    fields = body.model_dump(exclude_unset=True)
    row = update_incentive_for_review(
        conn,
        incentive_id,
        fields,
        reparse_raw_text=body.reparse_raw_text,
    )
    if not row:
        raise HTTPException(404, "incentive_not_found")
    return IncentiveCardOut.model_validate(row)


@router.post("/incentives/{incentive_id}/verify", response_model=IncentiveCardOut)
def admin_verify_incentive(
    conn: ConnDep,
    incentive_id: UUID,
    body: AdminIncentiveUpdate,
    admin: AdminUser,
) -> IncentiveCardOut:
    fields = body.model_dump(exclude_unset=True, exclude={"reparse_raw_text"})
    row = verify_incentive(conn, incentive_id, admin.id, fields=fields or None)
    if not row:
        raise HTTPException(404, "incentive_not_found")
    return IncentiveCardOut.model_validate(row)


@router.post("/incentives/{incentive_id}/reject", response_model=IncentiveCardOut)
def admin_reject_incentive(
    conn: ConnDep,
    incentive_id: UUID,
    body: AdminIncentiveRejectBody,
    admin: AdminUser,
) -> IncentiveCardOut:
    row = reject_incentive(conn, incentive_id, admin.id, reason=body.reason)
    if not row:
        raise HTTPException(404, "incentive_not_found")
    return IncentiveCardOut.model_validate(row)


@router.get("/sources")
def admin_list_sources(conn: ConnDep, _admin: AdminUser) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT s.id, s.building_id, s.url, s.source_type, s.crawl_strategy, s.wait_selector,
                   s.active, s.notes, s.metadata, s.created_at,
                   s.last_crawl_at, s.last_crawl_status, s.last_error, s.last_listings_count, s.last_parser_used,
                   b.name AS building_name, b.city
            FROM sources s
            JOIN buildings b ON b.id = s.building_id
            ORDER BY s.active DESC, b.name
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["status_bucket"] = source_status_bucket(r.get("last_crawl_status"))
        return rows


@router.get("/sources/status-summary")
def admin_sources_status_summary(conn: ConnDep, _admin: AdminUser) -> dict[str, Any]:
    """Blocked sources vs parser failures vs healthy — for ops dashboards."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT s.id, s.building_id, s.url, s.active,
                   s.last_crawl_at, s.last_crawl_status, s.last_error, s.last_listings_count,
                   b.name AS building_name, b.city
            FROM sources s
            JOIN buildings b ON b.id = s.building_id
            ORDER BY b.name
            """
        )
        rows = [dict(r) for r in cur.fetchall()]

    blocked: list[dict[str, Any]] = []
    parser_failures: list[dict[str, Any]] = []
    healthy: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []

    for r in rows:
        bucket = source_status_bucket(r.get("last_crawl_status"))
        r["status_bucket"] = bucket
        if bucket == "blocked":
            blocked.append(r)
        elif bucket == "parser_failure":
            parser_failures.append(r)
        elif bucket == "ok":
            healthy.append(r)
        else:
            other.append(r)

    return {
        "blocked": blocked,
        "parser_failures": parser_failures,
        "healthy": healthy,
        "other": other,
        "counts": {
            "blocked": len(blocked),
            "parser_failures": len(parser_failures),
            "healthy": len(healthy),
            "other": len(other),
            "total": len(rows),
        },
    }


@router.get("/crawl-runs")
def admin_crawl_runs(
    conn: ConnDep,
    _admin: AdminUser,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, started_at, finished_at, status, stats, error_message
            FROM crawl_runs
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/raw-documents")
def admin_raw_documents(
    conn: ConnDep,
    _admin: AdminUser,
    limit: int = Query(30, ge=1, le=200),
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, source_id, building_id, source_url, fetch_mode, format, http_status, captured_at
            FROM raw_documents
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/parser-health")
def admin_parser_health(_admin: AdminUser) -> dict[str, Any]:
    """Placeholder until per-parser metrics are persisted."""
    return {
        "parsers": [
            {"id": "next_data", "status": "ok", "note": "See crawler logs and last_parser_used on sources."},
            {"id": "generic_html", "status": "stub", "note": "Add selectors before expecting non-empty parses."},
        ]
    }


@router.get("/data-quality")
def admin_data_quality(conn: ConnDep, _admin: AdminUser) -> dict[str, Any]:
    """Lightweight SQL heuristics; expand in jobs/data_quality_check."""
    warnings: list[dict[str, Any]] = []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT s.id, s.url, b.name AS building_name
            FROM sources s
            JOIN buildings b ON b.id = s.building_id
            WHERE s.active = true
              AND (s.last_crawl_at IS NULL OR s.last_crawl_at < now() - interval '7 days')
            """
        )
        for r in cur.fetchall():
            warnings.append(
                {
                    "code": "stale_or_never_crawl",
                    "severity": "warning",
                    "source_id": str(r["id"]),
                    "building_name": r["building_name"],
                    "url": r["url"],
                }
            )
        cur.execute(
            """
            SELECT s.id, s.url, b.name AS building_name, s.last_listings_count, s.last_crawl_status
            FROM sources s
            JOIN buildings b ON b.id = s.building_id
            WHERE s.active = true
              AND s.last_listings_count = 0
              AND COALESCE(s.last_crawl_status, '') <> 'blocked'
            """
        )
        for r in cur.fetchall():
            warnings.append(
                {
                    "code": "zero_listings_last_crawl",
                    "severity": "warning",
                    "source_id": str(r["id"]),
                    "building_name": r["building_name"],
                    "url": r["url"],
                }
            )
        cur.execute(
            """
            SELECT s.id, s.url, b.name AS building_name, s.last_error, s.active
            FROM sources s
            JOIN buildings b ON b.id = s.building_id
            WHERE s.last_crawl_status = 'blocked'
            """
        )
        for r in cur.fetchall():
            warnings.append(
                {
                    "code": "source_blocked",
                    "severity": "error",
                    "source_id": str(r["id"]),
                    "building_name": r["building_name"],
                    "url": r["url"],
                    "message": r.get("last_error"),
                    "active": r.get("active"),
                }
            )
    return {"warnings": warnings}


@router.get("/users-entitlements")
def admin_users_entitlements(
    conn: ConnDep,
    _admin: AdminUser,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, u.email, u.is_admin,
                   ce.plan_code, ce.status, ce.starts_at, ce.expires_at, ce.source
            FROM users u
            LEFT JOIN customer_entitlements ce ON ce.user_id = u.id AND ce.status = 'active'
            ORDER BY u.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
