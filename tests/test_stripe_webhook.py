"""Stripe webhook and checkout entitlement tests."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.entitlement_service import EntitlementService
from app.services.stripe_webhook_service import process_stripe_event


def _checkout_completed_payload(
    *,
    session_id: str,
    user_id: UUID,
    plan_code: str = "hunt_pass_30",
    payment_status: str = "paid",
    payment_intent: str = "pi_test",
) -> dict:
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "payment_status": payment_status,
                "status": "complete",
                "customer": "cus_test",
                "subscription": f"sub_{uuid4().hex[:8]}",
                "payment_intent": payment_intent,
                "metadata": {"user_id": str(user_id), "plan_code": plan_code},
            }
        },
    }


def _stripe_event(payload: dict, *, event_id: str | None = None) -> dict:
    return {"id": event_id or f"evt_{uuid4().hex}", **payload}


def _insert_user(conn, email: str) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, name) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (email, "Stripe Test"),
        )
        uid = UUID(str(cur.fetchone()[0]))
    conn.commit()
    return uid


@pytest.mark.db
def test_checkout_completed_unpaid_does_not_grant(conn):
    uid = _insert_user(conn, f"stripe-unpaid-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_unpaid_{uuid4().hex[:8]}"
    process_stripe_event(
        conn,
        _checkout_completed_payload(session_id=session_id, user_id=uid, payment_status="unpaid"),
    )
    assert EntitlementService.has_active_hunt_pass(conn, uid) is False


@pytest.mark.db
def test_checkout_completed_paid_grants_30_day_hunt_pass(conn):
    uid = _insert_user(conn, f"stripe-paid-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_paid_{uuid4().hex[:8]}"
    process_stripe_event(
        conn,
        _checkout_completed_payload(session_id=session_id, user_id=uid, payment_status="paid"),
    )
    assert EntitlementService.has_active_hunt_pass(conn, uid) is True
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT starts_at, expires_at FROM customer_entitlements
            WHERE user_id = %s AND plan_code = 'hunt_pass_30' AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
            """,
            (str(uid),),
        )
        starts_at, expires_at = cur.fetchone()
    assert expires_at is not None
    delta_days = (expires_at - starts_at).days
    assert 29 <= delta_days <= 31


@pytest.mark.db
def test_checkout_expired_does_not_grant(conn):
    uid = _insert_user(conn, f"stripe-exp-nogrant-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_exp_{uuid4().hex[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO checkout_sessions (user_id, plan_code, amount_cents, currency, status, stripe_session_id)
            VALUES (%s, 'hunt_pass_30', 1900, 'USD', 'created', %s)
            """,
            (str(uid), session_id),
        )
    conn.commit()
    process_stripe_event(
        conn,
        {"type": "checkout.session.expired", "data": {"object": {"id": session_id}}},
    )
    assert EntitlementService.has_active_hunt_pass(conn, uid) is False


@pytest.mark.db
def test_duplicate_checkout_completed_does_not_double_grant(conn):
    uid = _insert_user(conn, f"stripe-dup-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_dup_{uuid4().hex[:8]}"
    payload = _checkout_completed_payload(session_id=session_id, user_id=uid)
    process_stripe_event(conn, payload)
    process_stripe_event(conn, payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM customer_entitlements
            WHERE user_id = %s AND plan_code = 'hunt_pass_30' AND status = 'active'
            """,
            (str(uid),),
        )
        count = cur.fetchone()[0]
    assert count == 1


@pytest.mark.db
def test_webhook_http_idempotency_by_event_id(conn, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_fake")
    monkeypatch.setenv("MOCK_CHECKOUT_MODE", "false")
    get_settings.cache_clear()

    uid = _insert_user(conn, f"stripe-http-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_http_{uuid4().hex[:8]}"
    event_id = f"evt_{uuid4().hex}"
    event = _stripe_event(
        _checkout_completed_payload(session_id=session_id, user_id=uid),
        event_id=event_id,
    )

    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)

        with patch("stripe.Webhook.construct_event", return_value=event):
            r1 = client.post(
                "/webhooks/stripe",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=test"},
            )
            r2 = client.post(
                "/webhooks/stripe",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=test"},
            )

        assert r1.status_code == 200
        assert r1.json()["received"] == "true"
        assert r2.status_code == 200
        assert r2.json().get("duplicate") == "true"
        assert EntitlementService.has_active_hunt_pass(conn, uid) is True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM stripe_webhook_events WHERE stripe_event_id = %s",
                (event_id,),
            )
            assert cur.fetchone()[0] == 1
    finally:
        close_pool()
        get_settings.cache_clear()


@pytest.mark.db
def test_payment_intent_failed_does_not_grant_new_access(conn):
    uid = _insert_user(conn, f"stripe-fail-{uuid4().hex[:8]}@example.com")
    process_stripe_event(
        conn,
        {
            "type": "payment_intent.payment_failed",
            "data": {"object": {"id": "pi_failed_new", "payment_intent": "pi_failed_new"}},
        },
    )
    assert EntitlementService.has_active_hunt_pass(conn, uid) is False


@pytest.mark.db
def test_duplicate_payment_intent_skips_second_grant(conn):
    uid = _insert_user(conn, f"stripe-pi-dup-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_pi_dup_{uuid4().hex[:8]}"
    payment_intent = f"pi_dup_{uuid4().hex[:8]}"
    payload = _checkout_completed_payload(
        session_id=session_id,
        user_id=uid,
        payment_intent=payment_intent,
    )
    process_stripe_event(conn, payload)
    process_stripe_event(conn, payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM customer_entitlements
            WHERE user_id = %s AND stripe_payment_intent_id = %s AND status = 'active'
            """,
            (str(uid), payment_intent),
        )
        assert cur.fetchone()[0] == 1


@pytest.mark.db
def test_completed_checkout_session_skips_regrant(conn):
    uid = _insert_user(conn, f"stripe-sess-done-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_done_{uuid4().hex[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO checkout_sessions (user_id, plan_code, amount_cents, currency, status, stripe_session_id)
            VALUES (%s, 'hunt_pass_30', 1900, 'USD', 'completed', %s)
            """,
            (str(uid), session_id),
        )
    conn.commit()
    process_stripe_event(
        conn,
        _checkout_completed_payload(
            session_id=session_id,
            user_id=uid,
            payment_intent=f"pi_new_{uuid4().hex[:8]}",
        ),
    )
    assert EntitlementService.has_active_hunt_pass(conn, uid) is False


@pytest.mark.db
def test_stripe_webhook_grants_full_deal_report(conn):
    from app.services.deal_report_service import DealReportService

    uid = _insert_user(conn, f"stripe-deal-{uuid4().hex[:8]}@example.com")
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM buildings ORDER BY slug LIMIT 1")
        row = cur.fetchone()
    assert row is not None
    building_id = UUID(str(row[0]))

    preview = DealReportService.build_report(
        conn, user_id=uid, building_id=building_id, unit_id=None, floorplan_id=None
    )
    assert preview["access"] == "preview"

    session_id = f"cs_deal_{uuid4().hex[:8]}"
    process_stripe_event(
        conn,
        _checkout_completed_payload(session_id=session_id, user_id=uid, payment_status="paid"),
    )
    assert EntitlementService.has_active_hunt_pass(conn, uid) is True

    full = DealReportService.build_report(
        conn, user_id=uid, building_id=building_id, unit_id=None, floorplan_id=None
    )
    assert full["access"] == "full"
    assert full["full_report"] is not None


@pytest.mark.db
def test_checkout_session_created_without_webhook_stays_free(conn):
    """Stripe redirect to /billing/success does not grant access — webhook only."""
    from app.services.deal_report_service import DealReportService

    uid = _insert_user(conn, f"stripe-no-webhook-{uuid4().hex[:8]}@example.com")
    session_id = f"cs_nowebhook_{uuid4().hex[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO checkout_sessions (user_id, plan_code, amount_cents, currency, status, stripe_session_id)
            VALUES (%s, 'hunt_pass_30', 1900, 'USD', 'created', %s)
            """,
            (str(uid), session_id),
        )
        cur.execute("SELECT id FROM buildings ORDER BY slug LIMIT 1")
        building_id = UUID(str(cur.fetchone()[0]))
    conn.commit()

    assert EntitlementService.has_active_hunt_pass(conn, uid) is False
    report = DealReportService.build_report(
        conn, user_id=uid, building_id=building_id, unit_id=None, floorplan_id=None
    )
    assert report["access"] == "preview"
