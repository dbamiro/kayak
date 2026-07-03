"""Subscription / pass entitlement checks (JWT user in API; anonymous treated as free for previews)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass
class UserEntitlementStatus:
    user_id: UUID
    email: str | None
    name: str | None
    active_plan_codes: list[str]
    expires_at_by_plan: dict[str, str | None]
    can_view_full_deal_reports: bool
    can_view_rent_history: bool
    can_view_fee_breakdown: bool
    can_use_negotiation_scripts: bool
    can_create_alerts: bool
    can_use_premium_compare: bool
    can_request_concierge: bool
    can_enhanced_report_export: bool


class EntitlementService:
    """Postgres-backed entitlements. Call `expire_old_entitlements` before reads."""

    PAID_SUBSCRIPTION_CODES = frozenset({"hunt_pass_30", "premium_plus_30"})
    PREMIUM_PLUS = "premium_plus_30"
    HUNT_PASS = "hunt_pass_30"
    CONCIERGE = "concierge_one_time"

    @staticmethod
    def expire_old_entitlements(conn: Connection) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customer_entitlements
                SET status = 'expired', updated_at = now()
                WHERE status = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at < now()
                """
            )
            return cur.rowcount or 0

    @staticmethod
    def _active_rows(conn: Connection, user_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT plan_code, expires_at, status
                FROM customer_entitlements
                WHERE user_id = %s AND status = 'active'
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY starts_at DESC
                """,
                (str(user_id),),
            )
            return list(cur.fetchall())

    @classmethod
    def has_active_hunt_pass(cls, conn: Connection, user_id: UUID) -> bool:
        for row in cls._active_rows(conn, user_id):
            if row["plan_code"] == cls.HUNT_PASS:
                return True
        return False

    @classmethod
    def has_premium_plus(cls, conn: Connection, user_id: UUID) -> bool:
        for row in cls._active_rows(conn, user_id):
            if row["plan_code"] == cls.PREMIUM_PLUS:
                return True
        return False

    @classmethod
    def has_concierge_purchase(cls, conn: Connection, user_id: UUID) -> bool:
        for row in cls._active_rows(conn, user_id):
            if row["plan_code"] == cls.CONCIERGE:
                return True
        return False

    @classmethod
    def has_paid_subscription(cls, conn: Connection, user_id: UUID) -> bool:
        return cls.has_active_hunt_pass(conn, user_id) or cls.has_premium_plus(conn, user_id)

    @classmethod
    def can_view_full_deal_report(
        cls,
        conn: Connection,
        user_id: UUID | None,
        building_id: UUID,
        unit_id: UUID | None = None,
        floorplan_id: UUID | None = None,
    ) -> bool:
        _ = (building_id, unit_id, floorplan_id)
        if user_id is None:
            return False
        return cls.has_paid_subscription(conn, user_id)

    @classmethod
    def get_user_status(cls, conn: Connection, user_id: UUID) -> UserEntitlementStatus:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, email, name FROM users WHERE id = %s",
                (str(user_id),),
            )
            u = cur.fetchone()
        if not u:
            raise LookupError("user_not_found")

        EntitlementService.expire_old_entitlements(conn)
        rows = cls._active_rows(conn, user_id)
        codes = [r["plan_code"] for r in rows]
        exp_map: dict[str, str | None] = {}
        for r in rows:
            exp = r["expires_at"]
            exp_map[r["plan_code"]] = exp.isoformat() if exp else None

        paid = cls.has_paid_subscription(conn, user_id)
        pp = cls.has_premium_plus(conn, user_id)
        concierge = cls.has_concierge_purchase(conn, user_id)

        return UserEntitlementStatus(
            user_id=user_id,
            email=u.get("email"),
            name=u.get("name"),
            active_plan_codes=codes,
            expires_at_by_plan=exp_map,
            can_view_full_deal_reports=paid,
            can_view_rent_history=paid,
            can_view_fee_breakdown=paid,
            can_use_negotiation_scripts=paid,
            can_create_alerts=paid,
            can_use_premium_compare=paid,
            can_request_concierge=pp or concierge,
            can_enhanced_report_export=pp,
        )

    @staticmethod
    def grant_entitlement(
        conn: Connection,
        *,
        user_id: UUID,
        plan_code: str,
        source: str,
        duration_days: int | None,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
        stripe_payment_intent_id: str | None = None,
    ) -> UUID:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT duration_days FROM plans WHERE code = %s AND is_active = true",
                (plan_code,),
            )
            plan = cur.fetchone()
            if not plan:
                raise ValueError("unknown_plan")
            eff_days = duration_days if duration_days is not None else plan["duration_days"]

            if eff_days is not None:
                cur.execute(
                    """
                    INSERT INTO customer_entitlements (
                        user_id, plan_code, starts_at, expires_at, status, source,
                        stripe_customer_id, stripe_subscription_id, stripe_payment_intent_id
                    )
                    VALUES (
                        %(uid)s, %(pc)s, now(),
                        now() + (%(days)s * interval '1 day'),
                        'active', %(src)s, %(sci)s, %(ssi)s, %(spi)s
                    )
                    RETURNING id
                    """,
                    {
                        "uid": str(user_id),
                        "pc": plan_code,
                        "days": int(eff_days),
                        "src": source,
                        "sci": stripe_customer_id,
                        "ssi": stripe_subscription_id,
                        "spi": stripe_payment_intent_id,
                    },
                )
            else:
                cur.execute(
                    """
                    INSERT INTO customer_entitlements (
                        user_id, plan_code, starts_at, expires_at, status, source,
                        stripe_customer_id, stripe_subscription_id, stripe_payment_intent_id
                    )
                    VALUES (
                        %(uid)s, %(pc)s, now(), NULL, 'active', %(src)s, %(sci)s, %(ssi)s, %(spi)s
                    )
                    RETURNING id
                    """,
                    {
                        "uid": str(user_id),
                        "pc": plan_code,
                        "src": source,
                        "sci": stripe_customer_id,
                        "ssi": stripe_subscription_id,
                        "spi": stripe_payment_intent_id,
                    },
                )
            row = cur.fetchone()
        conn.commit()
        return UUID(str(row["id"]))

    @staticmethod
    def cancel_by_subscription(conn: Connection, stripe_subscription_id: str) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customer_entitlements
                SET status = 'cancelled', updated_at = now()
                WHERE stripe_subscription_id = %s AND status = 'active'
                """,
                (stripe_subscription_id,),
            )
            n = cur.rowcount or 0
        conn.commit()
        return n

    @staticmethod
    def revoke_by_payment_intent(
        conn: Connection,
        stripe_payment_intent_id: str,
        *,
        status: str = "refunded",
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customer_entitlements
                SET status = %s, updated_at = now()
                WHERE stripe_payment_intent_id = %s AND status = 'active'
                """,
                (status, stripe_payment_intent_id),
            )
            n = cur.rowcount or 0
        conn.commit()
        return n

    @staticmethod
    def extend_subscription_period(conn: Connection, stripe_subscription_id: str) -> UUID | None:
        """Extend active pass by plan duration (30 days for Hunt Pass) on Stripe renewal."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, plan_code, expires_at
                FROM customer_entitlements
                WHERE stripe_subscription_id = %s AND status = 'active'
                ORDER BY expires_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                (stripe_subscription_id,),
            )
            ent = cur.fetchone()
            if not ent:
                return None
            cur.execute(
                "SELECT duration_days FROM plans WHERE code = %s AND is_active = true",
                (ent["plan_code"],),
            )
            plan = cur.fetchone()
            days = int(plan["duration_days"]) if plan and plan.get("duration_days") else 30
            cur.execute(
                """
                UPDATE customer_entitlements
                SET expires_at = GREATEST(COALESCE(expires_at, now()), now()) + (%s * interval '1 day'),
                    updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (days, str(ent["id"])),
            )
            row = cur.fetchone()
        conn.commit()
        return UUID(str(row["id"])) if row else None
