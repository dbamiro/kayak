"""Monetization tests — DB-backed tests use isolated kayak_test database."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.monetization import copy as paywall_copy
from app.services.entitlement_service import EntitlementService, UserEntitlementStatus


def test_paywall_copy_present():
    assert "Unlock" in paywall_copy.PAYWALL_HEADLINE
    assert paywall_copy.RECOMMENDED_PRICE_CENTS == 1900


def test_user_entitlement_status_flags():
    uid = uuid4()
    st = UserEntitlementStatus(
        user_id=uid,
        email="a@b.com",
        name="Test",
        active_plan_codes=["hunt_pass_30"],
        expires_at_by_plan={"hunt_pass_30": "2099-01-01T00:00:00+00:00"},
        can_view_full_deal_reports=True,
        can_view_rent_history=True,
        can_view_fee_breakdown=True,
        can_use_negotiation_scripts=True,
        can_create_alerts=True,
        can_use_premium_compare=True,
        can_request_concierge=False,
        can_enhanced_report_export=False,
    )
    from app.routers.monetization_api import _feature_flags_dict

    ff = _feature_flags_dict(st)
    assert ff["can_view_full_deal_reports"] is True
    assert ff["can_request_concierge"] is False


@pytest.mark.db
def test_plans_seeded():
    from app.db import get_pool

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM plans WHERE is_active ORDER BY code")
            codes = {r[0] for r in cur.fetchall()}
    assert "free" in codes
    assert "hunt_pass_30" in codes
    assert "premium_plus_30" in codes
    assert "concierge_one_time" in codes


@pytest.mark.db
def test_mock_checkout_grants_entitlement():
    from app.db import get_pool

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("monetization-test@example.com", "MTest"),
            )
            uid = UUID(str(cur.fetchone()[0]))
        conn.commit()
        EntitlementService.expire_old_entitlements(conn)
        EntitlementService.grant_entitlement(conn, user_id=uid, plan_code="hunt_pass_30", source="test", duration_days=None)
        assert EntitlementService.has_active_hunt_pass(conn, uid)


@pytest.mark.db
def test_deal_report_preview_vs_full():
    from app.db import get_pool
    from app.services.deal_report_service import DealReportService

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM buildings ORDER BY slug LIMIT 1")
            row = cur.fetchone()
        assert row is not None
        bid = UUID(str(row[0]))
        free_uid = uuid4()
        r_anon = DealReportService.build_report(
            conn, user_id=None, building_id=bid, unit_id=None, floorplan_id=None
        )
        assert r_anon["access"] == "preview"

        r_preview = DealReportService.build_report(
            conn, user_id=free_uid, building_id=bid, unit_id=None, floorplan_id=None
        )
        assert r_preview["access"] == "preview"
        assert r_preview["full_report"] is None
        assert "full_fee_breakdown" in r_preview["locked_sections"]

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("deal-paid@example.com", "Paid"),
            )
            paid_uid = UUID(str(cur.fetchone()[0]))
        conn.commit()
        EntitlementService.grant_entitlement(conn, user_id=paid_uid, plan_code="hunt_pass_30", source="test", duration_days=None)
        r_full = DealReportService.build_report(
            conn, user_id=paid_uid, building_id=bid, unit_id=None, floorplan_id=None
        )
        assert r_full["access"] == "full"
        assert r_full["full_report"] is not None
        assert "negotiation_script_email" in r_full["full_report"]


@pytest.mark.db
def test_concierge_requires_entitlement():
    pool = __import__("app.db", fromlist=["get_pool"]).get_pool()
    uid = uuid4()
    with pool.connection() as conn:
        EntitlementService.expire_old_entitlements(conn)
        ok = EntitlementService.has_premium_plus(conn, uid) or EntitlementService.has_concierge_purchase(conn, uid)
        assert ok is False


@pytest.mark.db
def test_hunt_pass_grants_30_day_duration():
    from app.db import get_pool

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("hunt-pass-duration@example.com", "Duration"),
            )
            uid = UUID(str(cur.fetchone()[0]))
        conn.commit()
        EntitlementService.grant_entitlement(
            conn, user_id=uid, plan_code="hunt_pass_30", source="test", duration_days=None
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT starts_at, expires_at FROM customer_entitlements WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                (str(uid),),
            )
            starts_at, expires_at = cur.fetchone()
        assert expires_at is not None
        delta_days = (expires_at - starts_at).days
        assert 29 <= delta_days <= 31


@pytest.mark.db
def test_expired_hunt_pass_removes_access():
    from app.db import get_pool
    from app.services.deal_report_service import DealReportService

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM buildings ORDER BY slug LIMIT 1")
            bid = UUID(str(cur.fetchone()[0]))
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("expired-hunt@example.com", "Expired"),
            )
            uid = UUID(str(cur.fetchone()[0]))
            cur.execute(
                """
                INSERT INTO customer_entitlements (
                    user_id, plan_code, starts_at, expires_at, status, source
                ) VALUES (%s, 'hunt_pass_30', now() - interval '40 days', now() - interval '1 day', 'active', 'test')
                """,
                (str(uid),),
            )
        conn.commit()
        EntitlementService.expire_old_entitlements(conn)
        assert EntitlementService.has_active_hunt_pass(conn, uid) is False
        report = DealReportService.build_report(conn, user_id=uid, building_id=bid, unit_id=None, floorplan_id=None)
        assert report["access"] == "preview"


@pytest.mark.db
def test_mock_checkout_http_flow(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    monkeypatch.setenv("MOCK_CHECKOUT_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    get_settings = __import__("app.config", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        email = f"checkout-{uuid4().hex[:8]}@example.com"
        reg = client.post("/auth/register", json={"email": email, "password": "testpassword123", "name": "Checkout"})
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        session = client.post("/checkout/session", headers=headers, json={"plan_code": "hunt_pass_30"})
        assert session.status_code == 200
        body = session.json()
        assert body["mock_mode"] is True

        complete = client.post(
            "/checkout/mock-complete", headers=headers, json={"plan_code": "hunt_pass_30"}
        )
        assert complete.status_code == 200
        assert complete.json()["feature_flags"]["can_view_full_deal_reports"] is True

        ent = client.get("/me/entitlements", headers=headers)
        assert ent.status_code == 200
        assert "hunt_pass_30" in ent.json()["active_plan_codes"]
    finally:
        close_pool()
        get_settings.cache_clear()


@pytest.mark.db
def test_mock_checkout_blocked_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    monkeypatch.setenv("MOCK_CHECKOUT_MODE", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    get_settings = __import__("app.config", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        email = f"prod-block-{uuid4().hex[:8]}@example.com"
        reg = client.post("/auth/register", json={"email": email, "password": "testpassword123"})
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = client.post("/checkout/mock-complete", headers=headers, json={"plan_code": "hunt_pass_30"})
        assert r.status_code == 403
    finally:
        close_pool()
        get_settings.cache_clear()


@pytest.mark.db
def test_stripe_webhook_checkout_completed_grants_hunt_pass():
    from app.db import get_pool
    from app.services.stripe_webhook_service import process_stripe_event

    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("stripe-webhook@example.com", "Stripe"),
            )
            uid = UUID(str(cur.fetchone()[0]))
        conn.commit()
        process_stripe_event(
            conn,
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": f"cs_test_{uuid4().hex[:8]}",
                        "payment_status": "paid",
                        "status": "complete",
                        "customer": "cus_test",
                        "subscription": "sub_test_grant",
                        "payment_intent": "pi_test_grant",
                        "metadata": {"user_id": str(uid), "plan_code": "hunt_pass_30"},
                    }
                },
            },
        )
        assert EntitlementService.has_active_hunt_pass(conn, uid) is True


@pytest.mark.db
def test_stripe_webhook_subscription_deleted_cancels_access():
    from app.db import get_pool
    from app.services.stripe_webhook_service import process_stripe_event

    pool = get_pool()
    sub_id = f"sub_del_{uuid4().hex[:8]}"
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("stripe-cancel@example.com", "Cancel"),
            )
            uid = UUID(str(cur.fetchone()[0]))
        conn.commit()
        EntitlementService.grant_entitlement(
            conn,
            user_id=uid,
            plan_code="hunt_pass_30",
            source="stripe",
            duration_days=None,
            stripe_subscription_id=sub_id,
        )
        assert EntitlementService.has_active_hunt_pass(conn, uid) is True
        process_stripe_event(
            conn,
            {"type": "customer.subscription.deleted", "data": {"object": {"id": sub_id}}},
        )
        assert EntitlementService.has_active_hunt_pass(conn, uid) is False


@pytest.mark.db
def test_stripe_webhook_checkout_expired_marks_session():
    from app.db import get_pool
    from app.services.stripe_webhook_service import process_stripe_event

    pool = get_pool()
    stripe_sess = f"cs_exp_{uuid4().hex[:8]}"
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                ("stripe-expired@example.com", "ExpiredSess"),
            )
            uid = UUID(str(cur.fetchone()[0]))
            cur.execute(
                """
                INSERT INTO checkout_sessions (user_id, plan_code, amount_cents, currency, status, stripe_session_id)
                VALUES (%s, 'hunt_pass_30', 1900, 'USD', 'created', %s)
                """,
                (str(uid), stripe_sess),
            )
        conn.commit()
        process_stripe_event(
            conn,
            {"type": "checkout.session.expired", "data": {"object": {"id": stripe_sess}}},
        )
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM checkout_sessions WHERE stripe_session_id = %s", (stripe_sess,))
            assert cur.fetchone()[0] == "expired"
