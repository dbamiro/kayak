"""Monetization API: plans, entitlements, checkout (Stripe + mock), Deal Reports, concierge, Stripe webhooks."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.deps import ConnDep
from app.deps_auth import CurrentUser, OptionalUser
from app.monetization.checkout_mode import (
    checkout_uses_stripe,
    mock_checkout_allowed,
    response_mock_mode,
    stripe_webhook_configured,
)
from app.services.deal_report_service import DealReportService
from app.services.entitlement_service import EntitlementService, UserEntitlementStatus
from app.services.stripe_checkout_service import create_stripe_checkout_session
from app.services.stripe_webhook_service import process_stripe_event
from psycopg.rows import dict_row
from psycopg.types.json import Json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monetization"])


# --- Users (MVP) ---


class UserCreate(BaseModel):
    email: str
    name: str | None = None


@router.post("/users", status_code=201)
def create_user(conn: ConnDep, body: UserCreate) -> dict[str, Any]:
    settings = get_settings()
    if settings.is_production():
        raise HTTPException(status_code=404, detail="not_found")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO users (email, name) VALUES (%(e)s, %(n)s)
            ON CONFLICT (email) DO UPDATE SET name = COALESCE(EXCLUDED.name, users.name), updated_at = now()
            RETURNING id, email, name, created_at
            """,
            {"e": body.email.lower().strip(), "n": body.name},
        )
        row = cur.fetchone()
    conn.commit()
    return dict(row)


@router.get("/users/{user_id}")
def get_user(conn: ConnDep, user_id: UUID) -> dict[str, Any]:
    if get_settings().is_production():
        raise HTTPException(status_code=404, detail="not_found")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, email, name, created_at FROM users WHERE id = %s", (str(user_id),))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="user_not_found")
    return dict(row)


# --- Plans ---


@router.get("/plans")
def list_plans(conn: ConnDep) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, code, name, price_cents, currency, duration_days, plan_type, description, is_active, created_at
            FROM plans WHERE is_active = true ORDER BY price_cents ASC NULLS FIRST
            """
        )
        return [dict(r) for r in cur.fetchall()]


# --- Me / entitlements ---


@router.get("/me/entitlements")
def me_entitlements(user: CurrentUser, conn: ConnDep) -> dict[str, Any]:
    try:
        st = EntitlementService.get_user_status(conn, user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="user_not_found") from None
    return {
        "user": {"id": str(st.user_id), "email": st.email, "name": st.name},
        "active_plan_codes": st.active_plan_codes,
        "expires_at_by_plan": st.expires_at_by_plan,
        "feature_flags": _feature_flags_dict(st),
    }


# --- Checkout ---


class CheckoutSessionBody(BaseModel):
    plan_code: str
    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/checkout/session")
def create_checkout_session(
    conn: ConnDep,
    user: CurrentUser,
    body: CheckoutSessionBody,
) -> dict[str, Any]:
    settings = get_settings()
    uid = user.id
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT code, price_cents, currency, duration_days FROM plans WHERE code = %s AND is_active",
            (body.plan_code,),
        )
        plan = cur.fetchone()
    if not plan or plan["code"] == "free":
        raise HTTPException(status_code=400, detail="invalid_plan")

    amount = int(plan["price_cents"])
    currency = plan["currency"] or "USD"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO checkout_sessions (user_id, plan_code, amount_cents, currency, status, checkout_url)
            VALUES (%(uid)s, %(pc)s, %(amt)s, %(cur)s, 'created', %(url)s)
            RETURNING id
            """,
            {
                "uid": str(uid),
                "pc": body.plan_code,
                "amt": amount,
                "cur": currency,
                "url": None,
            },
        )
        sid = UUID(str(cur.fetchone()["id"]))

    checkout_url: str | None = None
    stripe_session_id: str | None = None

    if checkout_uses_stripe(settings):
        try:
            checkout_url, stripe_session_id = create_stripe_checkout_session(
                settings,
                user_id=uid,
                plan_code=body.plan_code,
                checkout_session_row_id=sid,
                success_url=body.success_url,
                cancel_url=body.cancel_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("stripe_checkout_failed")
            raise HTTPException(status_code=502, detail=f"stripe_error: {exc}") from exc
    elif mock_checkout_allowed(settings):
        checkout_url = (
            f"{settings.api_base_url}/docs#/default/post_checkout_mock_complete "
            f"(dev: POST /checkout/mock-complete with Authorization: Bearer …; session_row={sid})"
        )
    else:
        raise HTTPException(
            status_code=503,
            detail="Checkout unavailable: configure Stripe or enable mock checkout for local dev",
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE checkout_sessions
            SET checkout_url = %s, stripe_session_id = %s, updated_at = now()
            WHERE id = %s
            """,
            (checkout_url, stripe_session_id, str(sid)),
        )
    conn.commit()

    return {
        "checkout_session_id": str(sid),
        "checkout_url": checkout_url,
        "stripe_session_id": stripe_session_id,
        "mock_mode": response_mock_mode(settings),
    }


def _feature_flags_dict(st: UserEntitlementStatus) -> dict[str, bool]:
    return {
        "can_view_full_deal_reports": st.can_view_full_deal_reports,
        "can_view_rent_history": st.can_view_rent_history,
        "can_view_fee_breakdown": st.can_view_fee_breakdown,
        "can_use_negotiation_scripts": st.can_use_negotiation_scripts,
        "can_create_alerts": st.can_create_alerts,
        "can_use_premium_compare": st.can_use_premium_compare,
        "can_request_concierge": st.can_request_concierge,
        "can_enhanced_report_export": st.can_enhanced_report_export,
    }


class MockCompleteBody(BaseModel):
    plan_code: str


@router.post("/checkout/mock-complete")
def mock_checkout_complete(conn: ConnDep, user: CurrentUser, body: MockCompleteBody) -> dict[str, Any]:
    settings = get_settings()
    if not mock_checkout_allowed(settings):
        raise HTTPException(status_code=403, detail="mock checkout disabled")

    if body.plan_code not in ("hunt_pass_30", "premium_plus_30", "concierge_one_time"):
        raise HTTPException(status_code=400, detail="invalid_plan_code_for_mock")

    uid = user.id

    EntitlementService.grant_entitlement(
        conn,
        user_id=uid,
        plan_code=body.plan_code,
        source="mock",
        duration_days=None,
    )
    st = EntitlementService.get_user_status(conn, uid)
    return {"ok": True, "feature_flags": _feature_flags_dict(st)}


def _deal_report_user_id(
    settings,
    user: OptionalUser,
    *,
    user_id: UUID | None,
    x_user_id: str | None,
) -> UUID | None:
    """Authenticated user from JWT, optional legacy headers in mock mode, or anonymous (None) for preview."""
    if user is not None:
        return user.id
    if settings.mock_auth_mode:
        if user_id is not None:
            return user_id
        if x_user_id:
            return UUID(x_user_id)
    return None


@router.get("/deal-reports/{building_id}")
def get_deal_report(
    conn: ConnDep,
    building_id: UUID,
    user: OptionalUser,
    user_id: UUID | None = None,
    unit_id: UUID | None = None,
    floorplan_id: UUID | None = None,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    settings = get_settings()
    uid = _deal_report_user_id(settings, user, user_id=user_id, x_user_id=x_user_id)
    try:
        return DealReportService.build_report(
            conn, user_id=uid, building_id=building_id, unit_id=unit_id, floorplan_id=floorplan_id
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="building_not_found") from None


class ConciergeRequestBody(BaseModel):
    target_city: str | None = None
    budget_min: Decimal | None = None
    budget_max: Decimal | None = None
    bedrooms: Decimal | None = None
    commute_target: str | None = None
    notes: str | None = None


@router.post("/concierge/request")
def concierge_request(conn: ConnDep, user: CurrentUser, body: ConciergeRequestBody) -> dict[str, Any]:
    EntitlementService.expire_old_entitlements(conn)
    ok = EntitlementService.has_premium_plus(conn, user.id) or EntitlementService.has_concierge_purchase(conn, user.id)
    if not ok:
        return {
            "ok": False,
            "paywall": {
                "headline": "Concierge requests require Premium Plus or Concierge purchase",
                "recommended_plan": "premium_plus_30",
                "alternate_plan": "concierge_one_time",
            },
        }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO concierge_requests (
                user_id, status, target_city, budget_min, budget_max, bedrooms, commute_target, notes
            )
            VALUES (%(uid)s, 'submitted', %(tc)s, %(bmin)s, %(bmax)s, %(br)s, %(ct)s, %(no)s)
            RETURNING id, status, created_at
            """,
            {
                "uid": str(user.id),
                "tc": body.target_city,
                "bmin": body.budget_min,
                "bmax": body.budget_max,
                "br": body.bedrooms,
                "ct": body.commute_target,
                "no": body.notes,
            },
        )
        row = cur.fetchone()
    conn.commit()
    return {
        "ok": True,
        "request": dict(row),
        "disclaimer": "Concierge fulfillment is manual — ops will contact you separately (placeholder).",
    }


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, conn: ConnDep) -> dict[str, str]:
    settings = get_settings()
    if not stripe_webhook_configured(settings):
        raise HTTPException(status_code=503, detail="stripe_webhook_not_configured")

    import stripe

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="missing_signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stripe_webhook_verify_failed: %s", exc)
        raise HTTPException(status_code=400, detail="invalid_signature") from exc

    etype = event["type"]
    eid = str(event.get("id") or "")
    if not eid:
        raise HTTPException(status_code=400, detail="missing_event_id")

    logger.info("stripe_webhook_event type=%s id=%s", etype, eid)

    raw_payload = Json(dict(event)) if isinstance(event, dict) else Json({"repr": str(event)})

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, status FROM stripe_webhook_events WHERE stripe_event_id = %s", (eid,))
        ex = cur.fetchone()
    if ex and ex.get("status") == "processed":
        return {"received": "true", "duplicate": "true"}

    if not ex:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stripe_webhook_events (stripe_event_id, event_type, raw_payload, status)
                VALUES (%s, %s, %s, 'received')
                """,
                (eid, etype, raw_payload),
            )
        conn.commit()
    elif ex.get("status") == "failed":
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE stripe_webhook_events
                SET status = 'received', error_message = NULL, raw_payload = %s, event_type = %s
                WHERE stripe_event_id = %s AND status = 'failed'
                """,
                (raw_payload, etype, eid),
            )
        conn.commit()

    err: str | None = None
    try:
        process_stripe_event(conn, dict(event))
    except Exception as exc:  # noqa: BLE001
        err = str(exc)[:2000]
        logger.exception("stripe_webhook_handler_error: %s", exc)

    with conn.cursor() as cur:
        if err:
            cur.execute(
                """
                UPDATE stripe_webhook_events
                SET status = 'failed', error_message = %s, processed_at = now()
                WHERE stripe_event_id = %s
                """,
                (err, eid),
            )
        else:
            cur.execute(
                """
                UPDATE stripe_webhook_events
                SET status = 'processed', processed_at = now()
                WHERE stripe_event_id = %s
                """,
                (eid,),
            )
    conn.commit()

    if err:
        raise HTTPException(status_code=500, detail="webhook_handler_failed") from None
    return {"received": "true"}