"""Admin incentive review: list, edit, verify, reject."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.services.incentive_service import (
    _calc_row,
    _incentive_to_metrics,
    _special_summary,
    get_incentive,
    merge_parsed_into_data,
)
from app.services.incentive_text_parser import parse_incentive_text


def list_incentives_for_admin(
    conn: Connection,
    *,
    status: str | None = None,
    capture_method: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = """
        SELECT i.*,
               b.name AS building_name, b.city, b.neighborhood, b.dmv_area::text AS dmv_area, b.slug,
               su.email AS submitted_by_email,
               ru.email AS reviewed_by_email
        FROM incentives i
        LEFT JOIN buildings b ON b.id = i.building_id
        LEFT JOIN users su ON su.id = i.submitted_by_user_id
        LEFT JOIN users ru ON ru.id = i.reviewed_by_user_id
        WHERE 1=1
    """
    params: list[Any] = []
    if status:
        sql += " AND i.status = %s"
        params.append(status)
    if capture_method:
        sql += " AND i.capture_method = %s"
        params.append(capture_method)
    sql += " ORDER BY i.created_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    out: list[dict[str, Any]] = []
    for row in rows:
        m = _incentive_to_metrics(row)
        item = {**row, "special_summary": _special_summary(row)}
        if m:
            item.update(m.__dict__)
        out.append(item)
    return out


def _append_snapshot(conn: Connection, inc: dict[str, Any], confidence: float | None = None) -> None:
    rent = inc.get("listed_rent")
    term = inc.get("lease_term_months")
    if not rent or not term:
        return
    calc = _calc_row(
        int(rent),
        int(term),
        float(inc.get("free_months") or 0),
        recurring_fee_monthly=int(inc.get("recurring_fee_monthly") or 0),
        one_time_fee=int(inc.get("one_time_fee") or 0),
        waived_fee_amount=int(inc.get("waived_fee_amount") or 0),
        gift_card_amount=int(inc.get("gift_card_amount") or 0),
        parking_discount_monthly=int(inc.get("parking_discount_monthly") or 0),
        custom_credit_amount=int(inc.get("custom_credit_amount") or 0),
    )
    conn.execute(
        """
        INSERT INTO incentive_snapshots (
            incentive_id, raw_text, free_months, lease_term_months, listed_rent,
            estimated_savings, effective_rent, all_in_effective_rent, confidence_score
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(inc["id"]),
            inc.get("raw_text"),
            inc.get("free_months"),
            inc.get("lease_term_months"),
            inc.get("listed_rent"),
            calc.total_savings,
            calc.effective_rent,
            calc.all_in_effective_rent,
            confidence if confidence is not None else inc.get("confidence_score"),
        ),
    )


def update_incentive_for_review(
    conn: Connection,
    incentive_id: UUID,
    fields: dict[str, Any],
    *,
    reparse_raw_text: bool = False,
) -> dict[str, Any] | None:
    existing = get_incentive(conn, incentive_id)
    if not existing:
        return None

    updates = dict(fields)
    if reparse_raw_text and updates.get("raw_text"):
        parsed = parse_incentive_text(str(updates["raw_text"]))
        merged = merge_parsed_into_data(
            {
                "incentive_type": existing.get("incentive_type"),
                "free_months": existing.get("free_months"),
                "waived_fee_amount": existing.get("waived_fee_amount"),
                "gift_card_amount": existing.get("gift_card_amount"),
                "custom_credit_amount": existing.get("custom_credit_amount"),
                **updates,
            },
            parsed,
        )
        updates.update(merged)

    allowed = {
        "building_id",
        "incentive_type",
        "free_months",
        "lease_term_months",
        "listed_rent",
        "waived_fee_amount",
        "gift_card_amount",
        "custom_credit_amount",
        "parking_discount_monthly",
        "recurring_fee_monthly",
        "one_time_fee",
        "raw_text",
        "applies_to",
        "expires_at",
        "source_url",
        "confidence_score",
        "verification_method",
    }
    set_parts: list[str] = []
    params: dict[str, Any] = {"id": str(incentive_id)}
    for key in allowed:
        if key not in updates or updates[key] is None:
            continue
        if key == "building_id":
            set_parts.append("building_id = %(building_id)s")
            params["building_id"] = str(updates[key])
        elif key == "expires_at" and isinstance(updates[key], datetime):
            set_parts.append("expires_at = %(expires_at)s")
            params["expires_at"] = updates[key]
        else:
            set_parts.append(f"{key} = %({key})s")
            params[key] = updates[key]

    if not set_parts:
        return existing

    set_parts.append("updated_at = now()")
    sql = f"UPDATE incentives SET {', '.join(set_parts)} WHERE id = %(id)s RETURNING *"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    conn.commit()
    return get_incentive(conn, incentive_id) if row else None


def verify_incentive(
    conn: Connection,
    incentive_id: UUID,
    reviewer_id: UUID,
    *,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if fields:
        updated = update_incentive_for_review(conn, incentive_id, fields, reparse_raw_text=False)
        if not updated:
            return None

    existing = get_incentive(conn, incentive_id)
    if not existing:
        return None

    confidence = max(float(existing.get("confidence_score") or 0.5), 0.85)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE incentives SET
                status = 'verified',
                is_demo = false,
                verified_at = now(),
                reviewed_at = now(),
                reviewed_by_user_id = %(reviewer)s,
                confidence_score = %(conf)s,
                updated_at = now()
            WHERE id = %(id)s
            RETURNING *
            """,
            {"id": str(incentive_id), "reviewer": str(reviewer_id), "conf": confidence},
        )
        row = cur.fetchone()
    if row:
        _append_snapshot(conn, dict(row), confidence)
    conn.commit()
    return get_incentive(conn, incentive_id)


def reject_incentive(
    conn: Connection,
    incentive_id: UUID,
    reviewer_id: UUID,
    *,
    reason: str | None = None,
) -> dict[str, Any] | None:
    existing = get_incentive(conn, incentive_id)
    if not existing:
        return None

    meta = dict(existing.get("metadata") or {})
    if reason:
        meta["rejection_reason"] = reason

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE incentives SET
                status = 'rejected',
                reviewed_at = now(),
                reviewed_by_user_id = %(reviewer)s,
                metadata = %(meta)s::jsonb,
                updated_at = now()
            WHERE id = %(id)s
            RETURNING id
            """,
            {"id": str(incentive_id), "reviewer": str(reviewer_id), "meta": Json(meta)},
        )
        row = cur.fetchone()
    conn.commit()
    return get_incentive(conn, incentive_id) if row else None
