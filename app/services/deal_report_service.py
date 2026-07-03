"""Deal Report: preview (free) vs full (paid) using existing listing/snapshot data."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from app.monetization import copy as paywall_copy
from app.services.entitlement_service import EntitlementService
from app.services.incentive_service import best_incentive_for_building

LOCKED_SECTIONS_PREVIEW = [
    "full_fee_breakdown",
    "rent_history",
    "negotiation_script",
    "comparable_deals",
    "price_drop_alerts",
]


class DealReportService:
    """Uses `buildings`, `listings`, `listing_snapshots`, `snapshot_*` — no dependency on optional analytics tables."""

    @staticmethod
    def _listing_filter(unit_id: UUID | None, floorplan_id: UUID | None) -> tuple[str, list[Any]]:
        if unit_id:
            return "AND l.unit_id = %s", [str(unit_id)]
        if floorplan_id:
            return "AND l.floorplan_id = %s", [str(floorplan_id)]
        return "", []

    @classmethod
    def _latest_metrics(cls, conn: Connection, building_id: UUID, unit_id: UUID | None, floorplan_id: UUID | None) -> dict[str, Any]:
        extra, params = cls._listing_filter(unit_id, floorplan_id)
        sql = f"""
            WITH latest AS (
                SELECT DISTINCT ON (ls.listing_id)
                    ls.listing_id,
                    ls.base_rent_monthly,
                    ls.effective_rent_monthly,
                    ls.all_in_monthly,
                    ls.leasing_pressure_score,
                    ls.negotiation_score,
                    ls.fees,
                    ls.concessions
                FROM listing_snapshots ls
                JOIN listings l ON l.id = ls.listing_id
                WHERE l.building_id = %s {extra}
                ORDER BY ls.listing_id, ls.captured_at DESC
            )
            SELECT
                MAX(base_rent_monthly) AS max_listed,
                AVG(effective_rent_monthly) AS avg_effective,
                AVG(all_in_monthly) AS avg_all_in,
                MAX(negotiation_score) AS max_neg_score,
                BOOL_OR(fees IS NOT NULL AND fees::text NOT IN ('{{}}', 'null')) AS has_fee_json,
                BOOL_OR(concessions IS NOT NULL AND concessions::text NOT IN ('{{}}', 'null')) AS has_conc_json
            FROM latest
        """
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [str(building_id), *params])
            row = cur.fetchone() or {}
        return dict(row)

    @classmethod
    def _rent_history(cls, conn: Connection, building_id: UUID, unit_id: UUID | None, floorplan_id: UUID | None) -> list[dict[str, Any]]:
        extra, params = cls._listing_filter(unit_id, floorplan_id)
        sql = f"""
            SELECT ls.captured_at, ls.base_rent_monthly, ls.effective_rent_monthly, ls.all_in_monthly,
                   ls.negotiation_score, l.id AS listing_id
            FROM listing_snapshots ls
            JOIN listings l ON l.id = ls.listing_id
            WHERE l.building_id = %s {extra}
            ORDER BY ls.captured_at ASC
        """
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [str(building_id), *params])
            return [dict(r) for r in cur.fetchall()]

    @classmethod
    def _fee_breakdown(cls, conn: Connection, building_id: UUID, unit_id: UUID | None, floorplan_id: UUID | None) -> list[dict[str, Any]]:
        extra, params = cls._listing_filter(unit_id, floorplan_id)
        sql = f"""
            SELECT sf.raw_text, sf.parser_confidence, ls.captured_at
            FROM snapshot_fees sf
            JOIN listing_snapshots ls ON ls.id = sf.listing_snapshot_id
            JOIN listings l ON l.id = ls.listing_id
            WHERE l.building_id = %s {extra}
            ORDER BY ls.captured_at DESC
            LIMIT 50
        """
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [str(building_id), *params])
            return [dict(r) for r in cur.fetchall()]

    @classmethod
    def _concession_history(cls, conn: Connection, building_id: UUID, unit_id: UUID | None, floorplan_id: UUID | None) -> list[dict[str, Any]]:
        extra, params = cls._listing_filter(unit_id, floorplan_id)
        sql = f"""
            SELECT sc.raw_text, sc.parser_confidence, ls.captured_at
            FROM snapshot_concessions sc
            JOIN listing_snapshots ls ON ls.id = sc.listing_snapshot_id
            JOIN listings l ON l.id = ls.listing_id
            WHERE l.building_id = %s {extra}
            ORDER BY ls.captured_at DESC
            LIMIT 50
        """
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [str(building_id), *params])
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def _deal_signal(neg_score: int | None) -> str:
        if neg_score is None:
            return "Fair"
        if neg_score >= 65:
            return "Strong"
        if neg_score >= 45:
            return "Fair"
        return "Weak"

    @staticmethod
    def _negotiation_level(neg_score: int | None) -> str:
        if neg_score is None:
            return "medium"
        if neg_score >= 60:
            return "high"
        if neg_score >= 40:
            return "medium"
        return "low"

    @classmethod
    def _comparable_deals(cls, conn: Connection, building_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT dmv_area::text FROM buildings WHERE id = %s", (str(building_id),))
            row = cur.fetchone()
            if not row:
                return []
            dmv = row["dmv_area"]
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (l.id)
                        b.name, b.id AS building_id, ls.all_in_monthly
                    FROM listings l
                    JOIN buildings b ON b.id = l.building_id
                    JOIN listing_snapshots ls ON ls.listing_id = l.id
                    WHERE b.dmv_area = %s::dmv_area AND b.id <> %s::uuid
                    ORDER BY l.id, ls.captured_at DESC
                )
                SELECT name, building_id, all_in_monthly
                FROM latest
                WHERE all_in_monthly IS NOT NULL
                ORDER BY all_in_monthly ASC
                LIMIT 5
                """,
                (dmv, str(building_id)),
            )
            return [dict(r) for r in cur.fetchall()]

    @classmethod
    def build_report(
        cls,
        conn: Connection,
        *,
        user_id: UUID | None,
        building_id: UUID,
        unit_id: UUID | None,
        floorplan_id: UUID | None,
    ) -> dict[str, Any]:
        EntitlementService.expire_old_entitlements(conn)
        full = EntitlementService.can_view_full_deal_report(conn, user_id, building_id, unit_id, floorplan_id)

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, name, city, dmv_area::text AS dmv_area FROM buildings WHERE id = %s",
                (str(building_id),),
            )
            b = cur.fetchone()
        if not b:
            raise LookupError("building_not_found")

        m = cls._latest_metrics(conn, building_id, unit_id, floorplan_id)
        inc = best_incentive_for_building(conn, building_id)
        max_listed = m.get("max_listed")
        avg_eff = m.get("avg_effective")
        neg = m.get("max_neg_score")
        neg_int = int(neg) if neg is not None else None

        listed = int(Decimal(str(max_listed))) if max_listed is not None else None
        eff = float(Decimal(str(avg_eff))) if avg_eff is not None else None
        eff_int = int(round(eff)) if eff is not None else None

        if inc and inc.get("listed_rent"):
            listed = int(inc["listed_rent"])
            eff_int = int(inc.get("effective_rent") or eff_int or 0)

        hidden = "Possible extra monthly fees detected" if m.get("has_fee_json") else "No obvious fee payload in latest snapshot"

        savings_range: dict[str, Any] | None = None
        incentive_summary: dict[str, Any] | None = None
        if inc:
            incentive_summary = {
                "special_text": inc.get("special_summary") or inc.get("raw_text"),
                "incentive_type": inc.get("incentive_type"),
                "free_months": float(inc["free_months"]) if inc.get("free_months") is not None else None,
                "lease_term_months": inc.get("lease_term_months"),
                "total_savings": inc.get("total_savings"),
                "effective_rent": inc.get("effective_rent"),
                "discount_percent": inc.get("discount_percent"),
                "all_in_effective_rent": inc.get("all_in_effective_rent"),
                "is_demo": inc.get("is_demo", False),
                "verified": inc.get("verified_at") is not None,
            }
            if inc.get("total_savings") is not None:
                savings_range = {
                    "min": int(inc["total_savings"]),
                    "max": int(inc["total_savings"]),
                    "basis": "incentive_calculator",
                    "disclaimer": "Based on parsed move-in special; confirm with leasing office.",
                }
        elif max_listed is not None and avg_eff is not None:
            try:
                spread = float(Decimal(str(max_listed)) - Decimal(str(avg_eff)))
                if spread > 0:
                    annual = int(round(spread * 12))
                    savings_range = {
                        "min": 0,
                        "max": annual,
                        "basis": "listed_minus_latest_effective_monthly_times_12",
                        "disclaimer": "Rough annualized spread from latest snapshot fields; not a guaranteed concession.",
                    }
            except Exception:  # noqa: BLE001
                savings_range = None

        preview = {
            "listed_rent": listed,
            "estimated_effective_rent": eff_int,
            "incentive": incentive_summary,
            "deal_signal": cls._deal_signal(neg_int),
            "negotiation_signal": cls._negotiation_level(neg_int),
            "potential_savings_range": savings_range,
            "hidden_fee_signal": hidden,
            "savings_disclaimer": paywall_copy.POTENTIAL_SAVINGS_COPY,
            "questions_for_leasing": [
                "Does this special apply to my exact unit and move-in date?",
                "What is the required lease length to qualify?",
                "Are admin or application fees waived or just discounted?",
            ],
        }

        paywall = {
            "headline": paywall_copy.PAYWALL_HEADLINE,
            "subheadline": paywall_copy.PAYWALL_SUBHEADLINE,
            "recommended_plan": paywall_copy.RECOMMENDED_PLAN_CODE,
            "price_cents": paywall_copy.RECOMMENDED_PRICE_CENTS,
            "cta": paywall_copy.PAYWALL_CTA,
            "value_bullets": paywall_copy.VALUE_BULLETS,
        }

        out: dict[str, Any] = {
            "building_id": str(building_id),
            "building_name": b["name"],
            "access": "full" if full else "preview",
            "preview": preview,
            "locked_sections": [] if full else LOCKED_SECTIONS_PREVIEW,
            "paywall": None if full else paywall,
            "full_report": None,
        }

        if not full:
            return out

        rent_hist = cls._rent_history(conn, building_id, unit_id, floorplan_id)
        fees = cls._fee_breakdown(conn, building_id, unit_id, floorplan_id)
        conc = cls._concession_history(conn, building_id, unit_id, floorplan_id)
        comps = cls._comparable_deals(conn, building_id)

        script_email = (
            f"Subject: Lease terms at {b['name']}\n\n"
            f"I'm interested in an apartment and would like to discuss the advertised rent, "
            f"current specials, and any flexibility on fees given current market conditions in {b['city']}."
        )
        script_phone = (
            f"Hi — I'm calling about {b['name']}. I'd like to understand the full monthly cost "
            f"(rent plus recurring fees) and whether there is room to negotiate given lease-up timing."
        )

        incentive_warnings: list[str] = []
        if inc:
            if inc.get("applies_to") and "select" in str(inc["applies_to"]).lower():
                incentive_warnings.append("Special may apply only to select units — confirm availability.")
            if inc.get("lease_term_months") and int(inc["lease_term_months"]) >= 15:
                incentive_warnings.append(
                    f"Special may require a {inc['lease_term_months']}-month lease — compare vs shorter terms."
                )
            if inc.get("is_demo"):
                incentive_warnings.append("DEMO incentive data — not a verified live special.")

        out["full_report"] = {
            "fee_breakdown": fees,
            "rent_history": rent_hist,
            "concession_history": conc,
            "incentive_detail": incentive_summary,
            "incentive_verification_checklist": [
                "Get the special in writing on the lease or addendum",
                "Confirm net effective rent after all fees",
                "Ask if special stacks with other offers",
                "Verify expiration date and unit eligibility",
            ],
            "lease_term_comparison": _lease_term_comparison(inc) if inc else None,
            "incentive_warnings": incentive_warnings,
            "negotiation_score": neg_int,
            "negotiation_script_email": _incentive_script_email(b, inc) if inc else script_email,
            "negotiation_script_phone": _incentive_script_phone(b, inc) if inc else script_phone,
            "recommended_asks": [
                "Ask whether any unadvertised specials apply for your move-in window.",
                "Request an itemized monthly fee sheet before applying.",
                "Confirm the advertised free months apply to your floorplan.",
            ],
            "comparable_deals": comps,
            "enhanced_export_placeholder": "Premium Plus: PDF/export pipeline not wired yet.",
            "shortlist_decision_placeholder": "Premium Plus: shortlist scoring UI not wired yet.",
            "wait_apply_negotiate_hint": "Compare effective rent after the special vs buildings without concessions before applying.",
        }
        return out


def _lease_term_comparison(inc: dict[str, Any]) -> list[dict[str, Any]] | None:
    rent = inc.get("listed_rent")
    term = inc.get("lease_term_months")
    fm = inc.get("free_months")
    if not rent or not term or fm is None:
        return None
    from app.services.incentive_calculator import calculate_effective_rent

    rows = []
    for alt_term in (12, int(term)):
        if alt_term <= 0:
            continue
        c = calculate_effective_rent(int(rent), alt_term, float(fm))
        rows.append(
            {
                "lease_term_months": alt_term,
                "effective_rent": c.effective_rent,
                "total_savings": c.total_savings,
            }
        )
    return rows or None


def _incentive_script_email(b: dict[str, Any], inc: dict[str, Any]) -> str:
    special = inc.get("special_summary") or "the current move-in special"
    return (
        f"Subject: {b['name']} — {special}\n\n"
        f"I'm interested in leasing and want to confirm the {special} applies to my unit and move-in date. "
        f"Can you provide the effective monthly rent after the concession and all recurring fees?"
    )


def _incentive_script_phone(b: dict[str, Any], inc: dict[str, Any]) -> str:
    special = inc.get("special_summary") or "move-in special"
    return (
        f"Hi — I'm calling about {b['name']}. I saw the {special} and want to confirm eligibility, "
        f"required lease length, and true effective rent including fees."
    )
