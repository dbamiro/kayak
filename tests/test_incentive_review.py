"""Admin incentive review workflow tests."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.incentive_review_service import reject_incentive, verify_incentive
from app.services.incentive_service import create_incentive, list_incentives_ranked, merge_parsed_into_data
from app.services.incentive_text_parser import parse_incentive_text


def _create_user(conn, email: str) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, name, is_admin)
            VALUES (%s, %s, false)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (email, "Test User"),
        )
        uid = UUID(str(cur.fetchone()[0]))
    conn.commit()
    return uid


def _create_admin(conn, email: str) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, name, is_admin)
            VALUES (%s, %s, true)
            ON CONFLICT (email) DO UPDATE SET is_admin = true
            RETURNING id
            """,
            (email, "Admin"),
        )
        uid = UUID(str(cur.fetchone()[0]))
    conn.commit()
    return uid


def _submit_pending(conn, *, building_id: UUID, submitter_id: UUID | None = None) -> UUID:
    parsed = parse_incentive_text("3 months free on 14-month lease")
    data = merge_parsed_into_data(
        {
            "building_id": building_id,
            "listed_rent": 2500,
            "lease_term_months": 14,
            "raw_text": "3 months free on 14-month lease",
            "status": "pending_review",
            "is_demo": False,
            "capture_method": "user_submission",
            "verification_method": "user_submitted",
            "submitted_by_user_id": submitter_id,
            "incentive_type": "free_months",
        },
        parsed,
    )
    row = create_incentive(conn, data)
    return UUID(str(row["id"]))


@pytest.mark.db
def test_pending_submission_not_in_public_list(conn):
    bid = UUID("b0000000-0000-4000-8000-000000000001")
    _submit_pending(conn, building_id=bid)
    public = list_incentives_ranked(conn, include_demo=False, limit=50)
    pending_in_public = [r for r in public if r.get("status") == "pending_review"]
    assert pending_in_public == []


@pytest.mark.db
def test_verify_makes_incentive_public(conn):
    bid = UUID("b0000000-0000-4000-8000-000000000001")
    admin_id = _create_admin(conn, f"admin-{uuid4().hex[:8]}@example.com")
    inc_id = _submit_pending(conn, building_id=bid)

    verified = verify_incentive(conn, inc_id, admin_id)
    assert verified is not None
    assert verified["status"] == "verified"
    assert verified["verified_at"] is not None
    assert verified["is_demo"] is False

    public = list_incentives_ranked(conn, building_id=bid, include_demo=False, limit=10)
    ids = {str(r["id"]) for r in public}
    assert str(inc_id) in ids


@pytest.mark.db
def test_reject_keeps_incentive_off_public_list(conn):
    bid = UUID("b0000000-0000-4000-8000-000000000001")
    admin_id = _create_admin(conn, f"admin-rej-{uuid4().hex[:8]}@example.com")
    inc_id = _submit_pending(conn, building_id=bid)

    rejected = reject_incentive(conn, inc_id, admin_id, reason="Could not confirm with leasing office")
    assert rejected is not None
    assert rejected["status"] == "rejected"

    public = list_incentives_ranked(conn, building_id=bid, include_demo=False, limit=10)
    assert str(inc_id) not in {str(r["id"]) for r in public}


@pytest.mark.db
def test_submit_incentive_api(conn):
    client = TestClient(app)
    r = client.post(
        "/incentives/submit",
        json={
            "building_name": "Kayak Test Alpha",
            "city": "Washington",
            "rent": 2400,
            "lease_term_months": 16,
            "raw_special_text": "2 months free for new leases",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending_review"
    assert body["is_demo"] is False


@pytest.mark.db
def test_admin_endpoints_require_admin(conn, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    admin_email = f"admin-api-{uuid4().hex[:8]}@example.com"
    monkeypatch.setenv("ADMIN_EMAILS", admin_email)
    get_settings.cache_clear()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)

        user_email = f"user-{uuid4().hex[:8]}@example.com"
        reg = client.post(
            "/auth/register",
            json={"email": user_email, "password": "testpassword123", "name": "User"},
        )
        user_token = reg.json()["access_token"]
        assert client.get("/admin/incentives", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403

        admin_reg = client.post(
            "/auth/register",
            json={"email": admin_email, "password": "testpassword123", "name": "Admin"},
        )
        assert admin_reg.status_code == 201
        admin_token = admin_reg.json()["access_token"]
        r_admin = client.get(
            "/admin/incentives?status=pending_review",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r_admin.status_code == 200
        assert isinstance(r_admin.json(), list)
    finally:
        close_pool()
        get_settings.cache_clear()
