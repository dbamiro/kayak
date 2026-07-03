"""Incentive-aware search enrichment, filtering, and ranking."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from app.queries import search_buildings
from app.services.incentive_service import _incentive_to_metrics, _public_status_sql, _special_summary
from app.services.demo_policy import resolve_include_demo

SearchSort = Literal["default", "savings", "effective_rent", "discount"]


def fetch_best_incentives_by_building(
    conn: Connection,
    building_ids: list[UUID],
    *,
    include_demo: bool = True,
) -> dict[str, dict[str, Any]]:
    """Return best active incentive per building (highest total_savings)."""
    if not building_ids:
        return {}
    ids = [str(b) for b in building_ids]
    demo_filter = "" if include_demo else " AND i.is_demo = false"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT i.*, b.name AS building_name
            FROM incentives i
            LEFT JOIN buildings b ON b.id = i.building_id
            WHERE i.building_id = ANY(%s::uuid[])
              AND (i.expires_at IS NULL OR i.expires_at > now())
              {_public_status_sql("i")}
              {demo_filter}
            """,
            (ids,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    best_by_building: dict[str, dict[str, Any]] = {}
    for row in rows:
        bid = str(row.get("building_id") or "")
        if not bid:
            continue
        metrics = _incentive_to_metrics(row)
        if not metrics:
            continue
        enriched = {
            **row,
            **metrics.__dict__,
            "estimated_savings": metrics.total_savings,
            "special_summary": _special_summary(row),
        }
        prev = best_by_building.get(bid)
        if prev is None or int(enriched["estimated_savings"]) > int(prev["estimated_savings"]):
            best_by_building[bid] = enriched
    return best_by_building


def incentive_fields_for_hit(inc: dict[str, Any]) -> dict[str, Any]:
    """Map best incentive row to SearchHit optional fields."""
    return {
        "best_incentive_id": inc.get("id"),
        "incentive_type": inc.get("incentive_type"),
        "raw_text": inc.get("raw_text"),
        "free_months": float(inc["free_months"]) if inc.get("free_months") is not None else None,
        "lease_term_months": inc.get("lease_term_months"),
        "listed_rent": inc.get("listed_rent"),
        "estimated_savings": inc.get("estimated_savings") or inc.get("total_savings"),
        "effective_rent": inc.get("effective_rent"),
        "all_in_effective_rent": inc.get("all_in_effective_rent"),
        "discount_percent": float(inc["discount_percent"]) if inc.get("discount_percent") is not None else None,
        "confidence_score": float(inc["confidence_score"]) if inc.get("confidence_score") is not None else None,
        "verified_at": inc.get("verified_at"),
        "incentive_is_demo": bool(inc.get("is_demo")),
    }


def _incentive_passes_filters(
    inc: dict[str, Any] | None,
    *,
    min_free_months: float | None,
    min_savings: int | None,
    max_effective_rent: int | None,
    has_incentive: bool | None,
) -> bool:
    if has_incentive and inc is None:
        return False
    if inc is None:
        return min_free_months is None and min_savings is None and max_effective_rent is None
    fm = float(inc.get("free_months") or 0)
    savings = int(inc.get("estimated_savings") or inc.get("total_savings") or 0)
    eff = inc.get("effective_rent")
    if min_free_months is not None and fm < min_free_months:
        return False
    if min_savings is not None and savings < min_savings:
        return False
    if max_effective_rent is not None:
        if eff is None or int(eff) > max_effective_rent:
            return False
    return True


def _listing_rent_fallback(row: dict[str, Any]) -> int | None:
    for key in ("effective_rent_monthly", "base_rent_monthly"):
        v = row.get(key)
        if v is not None:
            return int(Decimal(str(v)))
    return None


def _sort_key(row: dict[str, Any], sort: SearchSort) -> tuple:
    inc = row.get("_best_incentive")
    has_inc = inc is not None
    savings = int((inc or {}).get("estimated_savings") or (inc or {}).get("total_savings") or 0)
    discount = float((inc or {}).get("discount_percent") or 0)
    inc_eff = (inc or {}).get("effective_rent")
    listed_fallback = _listing_rent_fallback(row)

    if sort == "savings":
        return (
            0 if has_inc else 1,
            -savings,
            -discount,
            int(inc_eff) if inc_eff is not None else 999999,
            row.get("name") or "",
        )
    if sort == "effective_rent":
        eff = int(inc_eff) if inc_eff is not None else (listed_fallback or 999999)
        return (eff, row.get("name") or "")
    if sort == "discount":
        return (-discount if has_inc else 0, -savings, row.get("name") or "")
    return (row.get("name") or "", row.get("bedrooms") is None, row.get("bedrooms") or 0)


def enrich_and_rank_search(
    rows: list[dict[str, Any]],
    incentives_by_building: dict[str, dict[str, Any]],
    *,
    sort: SearchSort = "default",
    min_free_months: float | None = None,
    min_savings: int | None = None,
    max_effective_rent: int | None = None,
    has_incentive: bool | None = None,
) -> list[dict[str, Any]]:
    """Attach incentive fields, filter, and sort search rows."""
    incentive_filters_active = any(
        x is not None for x in (min_free_months, min_savings, max_effective_rent, has_incentive)
    )

    enriched: list[dict[str, Any]] = []
    for row in rows:
        bid = str(row["building_id"])
        inc = incentives_by_building.get(bid)
        if not _incentive_passes_filters(
            inc,
            min_free_months=min_free_months,
            min_savings=min_savings,
            max_effective_rent=max_effective_rent,
            has_incentive=has_incentive,
        ):
            continue
        if incentive_filters_active and inc is None and has_incentive is not True:
            if min_free_months is not None or min_savings is not None or max_effective_rent is not None:
                continue

        out = dict(row)
        out["_best_incentive"] = inc
        if inc:
            out.update(incentive_fields_for_hit(inc))
        else:
            out.update(
                {
                    "best_incentive_id": None,
                    "incentive_type": None,
                    "raw_text": None,
                    "free_months": None,
                    "lease_term_months": None,
                    "listed_rent": None,
                    "estimated_savings": None,
                    "effective_rent": None,
                    "all_in_effective_rent": None,
                    "discount_percent": None,
                    "confidence_score": None,
                    "verified_at": None,
                    "incentive_is_demo": None,
                }
            )
        enriched.append(out)

    enriched.sort(key=lambda r: _sort_key(r, sort))

    for row in enriched:
        row.pop("_best_incentive", None)
    return enriched


def search_listings_with_incentives(
    conn: Connection,
    *,
    city: str | None,
    dmv_area: str | None,
    min_rent: Decimal | None,
    max_rent: Decimal | None,
    bedrooms_min: Decimal | None,
    sort: SearchSort = "default",
    min_free_months: float | None = None,
    min_savings: int | None = None,
    max_effective_rent: int | None = None,
    has_incentive: bool | None = None,
    include_demo: bool | None = None,
) -> list[dict[str, Any]]:
    demo = resolve_include_demo(include_demo)
    rows = search_buildings(
        conn,
        city=city,
        dmv_area=dmv_area,
        min_rent=min_rent,
        max_rent=max_rent,
        bedrooms_min=bedrooms_min,
    )
    building_ids = list({UUID(str(r["building_id"])) for r in rows})
    incentives = fetch_best_incentives_by_building(conn, building_ids, include_demo=demo)
    return enrich_and_rank_search(
        rows,
        incentives,
        sort=sort,
        min_free_months=min_free_months,
        min_savings=min_savings,
        max_effective_rent=max_effective_rent,
        has_incentive=has_incentive,
    )
