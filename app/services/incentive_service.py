"""Incentive persistence, ranking, and deal-report integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.services.incentive_calculator import IncentiveCalculation, calculate_effective_rent
from app.services.incentive_text_parser import ParsedIncentive, format_incentive_headline, parse_incentive_text

# Public search/specials: verified real data only (legacy `active` = verified).
PUBLIC_INCENTIVE_STATUSES = ("active", "verified")


def _public_status_sql(alias: str = "i") -> str:
    statuses = ", ".join(f"'{s}'" for s in PUBLIC_INCENTIVE_STATUSES)
    return f" AND COALESCE({alias}.status, 'active') IN ({statuses})"


def _calc_row(
    listed_rent: int,
    lease_term_months: int,
    free_months: float = 0,
    **kwargs: int | float,
) -> IncentiveCalculation:
    return calculate_effective_rent(
        listed_rent,
        lease_term_months,
        free_months,
        recurring_fee_monthly=int(kwargs.get("recurring_fee_monthly") or 0),
        one_time_fee=int(kwargs.get("one_time_fee") or 0),
        waived_fee_amount=int(kwargs.get("waived_fee_amount") or 0),
        gift_card_amount=int(kwargs.get("gift_card_amount") or 0),
        parking_discount_monthly=int(kwargs.get("parking_discount_monthly") or 0),
        custom_credit_amount=int(kwargs.get("custom_credit_amount") or 0),
    )


def _incentive_to_metrics(row: dict[str, Any]) -> IncentiveCalculation | None:
    rent = row.get("listed_rent")
    term = row.get("lease_term_months")
    if rent is None or term is None:
        return None
    return _calc_row(
        int(rent),
        int(term),
        float(row.get("free_months") or 0),
        recurring_fee_monthly=int(row.get("recurring_fee_monthly") or 0),
        one_time_fee=int(row.get("one_time_fee") or 0),
        waived_fee_amount=int(row.get("waived_fee_amount") or 0),
        gift_card_amount=int(row.get("gift_card_amount") or 0),
        parking_discount_monthly=int(row.get("parking_discount_monthly") or 0),
        custom_credit_amount=int(row.get("custom_credit_amount") or 0),
    )


def _demo_sql_clause(include_demo: bool) -> str:
    return "" if include_demo else " AND i.is_demo = false"


def _special_summary(row: dict[str, Any]) -> str:
    return format_incentive_headline(row)


def merge_parsed_into_data(data: dict[str, Any], parsed: ParsedIncentive) -> dict[str, Any]:
    """Overlay parsed fields; explicit body values win when already set."""
    out = dict(data)
    if parsed.incentive_type != "unknown":
        out.setdefault("incentive_type", parsed.incentive_type)
    if parsed.free_months is not None and out.get("free_months") is None:
        out["free_months"] = parsed.free_months
    if parsed.weeks_free is not None:
        meta = dict(out.get("metadata") or {})
        meta["weeks_free"] = parsed.weeks_free
        out["metadata"] = meta
    for field in (
        "waived_fee_amount",
        "gift_card_amount",
        "parking_discount_monthly",
        "custom_credit_amount",
    ):
        if getattr(parsed, field) is not None and not out.get(field):
            out[field] = getattr(parsed, field)
    if parsed.confidence_score and not out.get("confidence_score"):
        out["confidence_score"] = parsed.confidence_score
    return out


def list_incentives_ranked(
    conn: Connection,
    *,
    building_id: UUID | None = None,
    city: str | None = None,
    dmv_area: str | None = None,
    neighborhood: str | None = None,
    min_free_months: float | None = None,
    min_savings: int | None = None,
    bedrooms: float | None = None,
    max_effective_rent: int | None = None,
    include_demo: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT i.*, b.name AS building_name, b.city, b.neighborhood, b.dmv_area::text AS dmv_area, b.slug
        FROM incentives i
        LEFT JOIN buildings b ON b.id = i.building_id
        WHERE (i.expires_at IS NULL OR i.expires_at > now())
          {_public_status_sql("i")}
          {_demo_sql_clause(include_demo)}
    """
    params: list[Any] = []
    if building_id:
        sql += " AND i.building_id = %s"
        params.append(str(building_id))
    if city:
        sql += " AND b.city ILIKE %s"
        params.append(f"%{city}%")
    if dmv_area:
        sql += " AND b.dmv_area = %s::dmv_area"
        params.append(dmv_area)
    if neighborhood:
        sql += " AND b.neighborhood ILIKE %s"
        params.append(f"%{neighborhood}%")
    if min_free_months is not None:
        sql += " AND COALESCE(i.free_months, 0) >= %s"
        params.append(min_free_months)
    sql += " ORDER BY i.created_at DESC LIMIT %s"
    params.append(limit * 3)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    out: list[dict[str, Any]] = []
    for row in rows:
        metrics = _incentive_to_metrics(row)
        if not metrics:
            continue
        if min_savings is not None and metrics.total_savings < min_savings:
            continue
        if max_effective_rent is not None and metrics.effective_rent > max_effective_rent:
            continue
        if bedrooms is not None and row.get("metadata"):
            meta_beds = (row.get("metadata") or {}).get("bedrooms")
            if meta_beds is not None and float(meta_beds) != float(bedrooms):
                continue
        item = {**row, **metrics.__dict__, "special_summary": _special_summary(row)}
        out.append(item)

    out.sort(
        key=lambda x: (
            -int(x.get("total_savings") or 0),
            -float(x.get("discount_percent") or 0),
            int(x.get("effective_rent") or 999999),
        )
    )
    return out[:limit]


def get_incentive(conn: Connection, incentive_id: UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT i.*, b.name AS building_name, b.city, b.neighborhood, b.dmv_area::text AS dmv_area
            FROM incentives i
            LEFT JOIN buildings b ON b.id = i.building_id
            WHERE i.id = %s
            """,
            (str(incentive_id),),
        )
        row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    m = _incentive_to_metrics(d)
    if m:
        d.update(m.__dict__)
    d["special_summary"] = _special_summary(d)
    return d


def create_incentive(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    calc = None
    if data.get("listed_rent") and data.get("lease_term_months"):
        calc = _calc_row(
            int(data["listed_rent"]),
            int(data["lease_term_months"]),
            float(data.get("free_months") or 0),
            recurring_fee_monthly=int(data.get("recurring_fee_monthly") or 0),
            one_time_fee=int(data.get("one_time_fee") or 0),
            waived_fee_amount=int(data.get("waived_fee_amount") or 0),
            gift_card_amount=int(data.get("gift_card_amount") or 0),
            parking_discount_monthly=int(data.get("parking_discount_monthly") or 0),
            custom_credit_amount=int(data.get("custom_credit_amount") or 0),
        )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO incentives (
                building_id, submitted_listing_id, submitted_by_user_id, source_url, incentive_type,
                free_months, lease_term_months, listed_rent, recurring_fee_monthly, one_time_fee,
                waived_fee_amount, gift_card_amount, parking_discount_monthly, custom_credit_amount,
                raw_text, applies_to, expires_at, verification_method, capture_method,
                confidence_score, is_demo, status, metadata, verified_at, reviewed_at, reviewed_by_user_id
            ) VALUES (
                %(building_id)s, %(submitted_listing_id)s, %(submitted_by_user_id)s, %(source_url)s,
                %(incentive_type)s, %(free_months)s, %(lease_term_months)s, %(listed_rent)s,
                %(recurring_fee_monthly)s, %(one_time_fee)s, %(waived_fee_amount)s, %(gift_card_amount)s,
                %(parking_discount_monthly)s, %(custom_credit_amount)s, %(raw_text)s, %(applies_to)s,
                %(expires_at)s, %(verification_method)s, %(capture_method)s, %(confidence_score)s,
                %(is_demo)s, %(status)s, %(metadata)s::jsonb, %(verified_at)s, %(reviewed_at)s,
                %(reviewed_by_user_id)s
            )
            RETURNING *
            """,
            {
                "building_id": str(data["building_id"]) if data.get("building_id") else None,
                "submitted_listing_id": str(data["submitted_listing_id"])
                if data.get("submitted_listing_id")
                else None,
                "submitted_by_user_id": str(data["submitted_by_user_id"])
                if data.get("submitted_by_user_id")
                else None,
                "source_url": data.get("source_url"),
                "incentive_type": data["incentive_type"],
                "free_months": data.get("free_months"),
                "lease_term_months": data.get("lease_term_months"),
                "listed_rent": data.get("listed_rent"),
                "recurring_fee_monthly": data.get("recurring_fee_monthly", 0),
                "one_time_fee": data.get("one_time_fee", 0),
                "waived_fee_amount": data.get("waived_fee_amount", 0),
                "gift_card_amount": data.get("gift_card_amount", 0),
                "parking_discount_monthly": data.get("parking_discount_monthly", 0),
                "custom_credit_amount": data.get("custom_credit_amount", 0),
                "raw_text": data.get("raw_text"),
                "applies_to": data.get("applies_to"),
                "expires_at": data.get("expires_at"),
                "verification_method": data.get("verification_method"),
                "capture_method": data.get("capture_method"),
                "confidence_score": data.get("confidence_score", 0.5),
                "is_demo": data.get("is_demo", False),
                "status": data.get("status", "active"),
                "metadata": Json(data.get("metadata") or {}),
                "verified_at": data.get("verified_at"),
                "reviewed_at": data.get("reviewed_at"),
                "reviewed_by_user_id": str(data["reviewed_by_user_id"])
                if data.get("reviewed_by_user_id")
                else None,
            },
        )
        inc = dict(cur.fetchone())
        if calc:
            cur.execute(
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
                    inc.get("confidence_score"),
                ),
            )
        if data.get("source_url") and data.get("capture_method"):
            cur.execute(
                """
                INSERT INTO incentive_sources (building_id, source_url, source_type, capture_method, active, last_status)
                VALUES (%s, %s, %s, %s, true, 'recorded')
                """,
                (
                    inc.get("building_id"),
                    data.get("source_url"),
                    data.get("incentive_type"),
                    data.get("capture_method"),
                ),
            )
    conn.commit()
    return get_incentive(conn, UUID(str(inc["id"]))) or inc


def best_incentive_for_building(
    conn: Connection,
    building_id: UUID,
    *,
    include_demo: bool = True,
) -> dict[str, Any] | None:
    demo_clause = _demo_sql_clause(include_demo)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT i.*, b.name AS building_name, b.city, b.neighborhood, b.dmv_area::text AS dmv_area
            FROM incentives i
            LEFT JOIN buildings b ON b.id = i.building_id
            WHERE i.building_id = %s
              AND (i.expires_at IS NULL OR i.expires_at > now())
              {_public_status_sql("i")}
              {demo_clause}
            ORDER BY i.created_at DESC
            """,
            (str(building_id),),
        )
        rows = [dict(r) for r in cur.fetchall()]
    best: dict[str, Any] | None = None
    best_savings = -1
    for row in rows:
        m = _incentive_to_metrics(row)
        if not m:
            continue
        if m.total_savings > best_savings:
            best_savings = m.total_savings
            best = {**row, **m.__dict__, "special_summary": _special_summary(row)}
    return best


def parse_and_calculate(
    raw_text: str,
    listed_rent: int | None,
    lease_term_months: int | None,
) -> dict[str, Any]:
    parsed: ParsedIncentive = parse_incentive_text(raw_text)
    out: dict[str, Any] = {
        "parsed": {
            "incentive_type": parsed.incentive_type,
            "free_months": parsed.free_months,
            "weeks_free": parsed.weeks_free,
            "waived_fee_amount": parsed.waived_fee_amount,
            "gift_card_amount": parsed.gift_card_amount,
            "parking_discount_monthly": parsed.parking_discount_monthly,
            "custom_credit_amount": parsed.custom_credit_amount,
            "confidence_score": parsed.confidence_score,
        },
        "calculation": None,
    }
    if listed_rent and lease_term_months:
        calc = calculate_effective_rent(
            listed_rent,
            lease_term_months,
            parsed.free_months or 0,
            waived_fee_amount=parsed.waived_fee_amount or 0,
            gift_card_amount=parsed.gift_card_amount or 0,
            parking_discount_monthly=parsed.parking_discount_monthly or 0,
            custom_credit_amount=parsed.custom_credit_amount or 0,
        )
        out["calculation"] = calc.__dict__
    return out


def resolve_building_id(conn: Connection, *, building_name: str | None, city: str | None) -> UUID | None:
    if not building_name:
        return None
    with conn.cursor(row_factory=dict_row) as cur:
        if city:
            cur.execute(
                "SELECT id FROM buildings WHERE name ILIKE %s AND city ILIKE %s LIMIT 1",
                (building_name, f"%{city}%"),
            )
        else:
            cur.execute("SELECT id FROM buildings WHERE name ILIKE %s LIMIT 1", (building_name,))
        row = cur.fetchone()
    return UUID(str(row["id"])) if row else None
