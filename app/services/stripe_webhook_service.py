"""Apply verified Stripe webhook events to entitlements and checkout sessions."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg import Connection

from app.services.entitlement_service import EntitlementService

logger = logging.getLogger(__name__)


def process_stripe_event(conn: Connection, event: dict[str, Any]) -> None:
    etype = event.get("type") or ""
    data = event.get("data", {}).get("object", {}) or {}

    if etype == "checkout.session.completed":
        _handle_checkout_completed(conn, data)
    elif etype == "checkout.session.expired":
        _handle_checkout_expired(conn, data)
    elif etype == "invoice.payment_succeeded":
        _handle_invoice_payment_succeeded(conn, data)
    elif etype == "payment_intent.succeeded":
        logger.info("stripe_payment_intent_succeeded id=%s", data.get("id"))
    elif etype in ("charge.refunded", "payment_intent.payment_failed"):
        _handle_payment_revoked(conn, data, etype)
    elif etype == "customer.subscription.deleted":
        _handle_subscription_deleted(conn, data)
    elif etype == "customer.subscription.updated":
        _handle_subscription_updated(conn, data)
    else:
        logger.info("stripe_webhook_unhandled type=%s", etype)


def _handle_checkout_completed(conn: Connection, session: dict[str, Any]) -> None:
    stripe_sess = session.get("id")
    if not stripe_sess:
        return

    payment_status = (session.get("payment_status") or "").lower()
    if payment_status != "paid":
        logger.info(
            "stripe_checkout_skip_grant session=%s payment_status=%s",
            stripe_sess,
            payment_status or "missing",
        )
        return

    payment_intent = session.get("payment_intent")
    if payment_intent:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM customer_entitlements
                WHERE stripe_payment_intent_id = %s AND status IN ('active', 'cancelled', 'refunded')
                LIMIT 1
                """,
                (str(payment_intent),),
            )
            if cur.fetchone():
                logger.info("stripe_checkout_skip_grant duplicate payment_intent=%s", payment_intent)
                with conn.cursor() as cur2:
                    cur2.execute(
                        """
                        UPDATE checkout_sessions
                        SET status = 'completed', updated_at = now()
                        WHERE stripe_session_id = %s AND status <> 'completed'
                        """,
                        (stripe_sess,),
                    )
                conn.commit()
                return

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM checkout_sessions WHERE stripe_session_id = %s",
            (stripe_sess,),
        )
        row = cur.fetchone()
    if row and row[0] == "completed":
        return

    meta = session.get("metadata") or {}
    uid = meta.get("user_id")
    pcode = meta.get("plan_code")
    if uid and pcode and pcode != "free":
        try:
            EntitlementService.grant_entitlement(
                conn,
                user_id=UUID(str(uid)),
                plan_code=str(pcode),
                source="stripe",
                duration_days=None,
                stripe_customer_id=str(session.get("customer")) if session.get("customer") else None,
                stripe_subscription_id=str(session.get("subscription")) if session.get("subscription") else None,
                stripe_payment_intent_id=str(session.get("payment_intent"))
                if session.get("payment_intent")
                else None,
            )
        except ValueError as exc:
            logger.warning("stripe_checkout_grant_skipped: %s", exc)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE checkout_sessions
            SET status = 'completed', updated_at = now()
            WHERE stripe_session_id = %s
            """,
            (stripe_sess,),
        )
    conn.commit()


def _handle_checkout_expired(conn: Connection, session: dict[str, Any]) -> None:
    stripe_sess = session.get("id")
    if not stripe_sess:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE checkout_sessions
            SET status = 'expired', updated_at = now()
            WHERE stripe_session_id = %s AND status = 'created'
            """,
            (stripe_sess,),
        )
    conn.commit()


def _handle_invoice_payment_succeeded(conn: Connection, invoice: dict[str, Any]) -> None:
    """Extend Hunt Pass / Premium Plus on subscription renewal."""
    if invoice.get("billing_reason") == "subscription_create":
        return
    sub_id = invoice.get("subscription")
    if not sub_id:
        return
    EntitlementService.extend_subscription_period(conn, str(sub_id))


def _handle_payment_revoked(conn: Connection, obj: dict[str, Any], etype: str) -> None:
    payment_intent = obj.get("payment_intent") or obj.get("id")
    if not payment_intent:
        return
    if etype == "charge.refunded":
        EntitlementService.revoke_by_payment_intent(conn, str(payment_intent), status="refunded")
    else:
        EntitlementService.revoke_by_payment_intent(conn, str(payment_intent), status="cancelled")


def _handle_subscription_deleted(conn: Connection, subscription: dict[str, Any]) -> None:
    sub_id = subscription.get("id")
    if sub_id:
        EntitlementService.cancel_by_subscription(conn, str(sub_id))


def _handle_subscription_updated(conn: Connection, subscription: dict[str, Any]) -> None:
    status = (subscription.get("status") or "").lower()
    sub_id = subscription.get("id")
    if not sub_id:
        return
    if status in ("canceled", "unpaid", "incomplete_expired"):
        EntitlementService.cancel_by_subscription(conn, str(sub_id))
