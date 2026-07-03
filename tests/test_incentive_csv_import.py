"""Admin CSV incentive import tests."""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.incentive_csv_import import parse_csv_rows, validate_and_import_csv
from app.services.incentive_service import list_incentives_ranked


VALID_CSV = """\
building_name,address,city,state,neighborhood,source_url,listed_rent,lease_months,free_months,free_weeks,rent_credit,waived_fees,expires_at,notes
Import Test Tower,500 Import Ln,Arlington,VA,Courthouse,https://leasing.import-test.invalid/special-a,2650,14,1.5,,300,200,2026-12-31,Verified by leasing office call
Kayak Test Alpha,100 Test St NW,Washington,DC,Logan Circle,https://leasing.import-test.invalid/alpha-special,2300,12,2,,,,2026-10-15,Existing building match
"""

USER_SCHEMA_CSV = """\
building_name,address,city,state,market,source_url,listed_rent,lease_months,free_weeks,expires_at,notes
Schema Alias Tower,700 Alias Rd,Reston,VA,Reston Town Center,https://leasing.import-test.invalid/schema,2550,13,4,2026-09-01,Uses market column alias
"""

MALFORMED_CSV = """\
building_name,address,city,state,listed_rent,lease_months,source_url,free_months
Bad Row,1 X St,Arlington,VA,,12,https://leasing.import-test.invalid/x,1
Good Row,2 Y St,Arlington,VA,2400,14,https://leasing.import-test.invalid/y,2
"""

EXAMPLE_CSV = """\
building_name,listed_rent,lease_months,source_url,free_months,address,city,state
[EXAMPLE ONLY] Fake Place,2400,14,https://example.com/fake,2,1 Fake St,Arlington,VA
"""


@pytest.mark.db
def test_parse_csv_normalizes_headers():
    content = "Building Name,Listed Rent,Lease Term Months,Source URL,Free Months\nX,2000,12,https://x.test/a,1\n"
    rows, errors = parse_csv_rows(content)
    assert not errors
    assert rows[0]["building_name"] == "X"
    assert rows[0]["listed_rent"] == "2000"


@pytest.mark.db
def test_valid_csv_import_creates_verified_public_incentives(conn):
    admin_id = _ensure_admin(conn, f"csv-admin-{uuid4().hex[:8]}@example.com")
    before = len(list_incentives_ranked(conn, include_demo=False, limit=100))

    result = validate_and_import_csv(conn, VALID_CSV, admin_user_id=admin_id, dry_run=False)
    assert result.error_count == 0
    assert result.created_count == 2
    assert len(result.created_incentive_ids) == 2

    public = list_incentives_ranked(conn, include_demo=False, limit=100)
    assert len(public) >= before + 2
    imported = [r for r in public if r.get("capture_method") == "admin_csv_import"]
    assert len(imported) >= 2
    for row in imported:
        assert row["is_demo"] is False
        assert row["status"] == "verified"
        assert row.get("verification_method") == "admin_csv_verified"


@pytest.mark.db
def test_malformed_rows_report_errors_and_skip(conn):
    admin_id = _ensure_admin(conn, f"csv-bad-{uuid4().hex[:8]}@example.com")
    result = validate_and_import_csv(conn, MALFORMED_CSV, admin_user_id=admin_id, dry_run=False)
    assert result.created_count == 1
    assert result.error_count >= 1
    assert any(e.row == 2 and e.field == "listed_rent" for e in result.errors)


@pytest.mark.db
def test_example_rows_rejected(conn):
    admin_id = _ensure_admin(conn, f"csv-ex-{uuid4().hex[:8]}@example.com")
    result = validate_and_import_csv(conn, EXAMPLE_CSV, admin_user_id=admin_id, dry_run=False)
    assert result.created_count == 0
    assert result.error_count >= 1
    assert any("example" in e.message.lower() for e in result.errors)


@pytest.mark.db
def test_user_schema_column_aliases_import(conn):
    admin_id = _ensure_admin(conn, f"csv-schema-{uuid4().hex[:8]}@example.com")
    result = validate_and_import_csv(conn, USER_SCHEMA_CSV, admin_user_id=admin_id, dry_run=False)
    assert result.error_count == 0
    assert result.created_count == 1

    public = list_incentives_ranked(conn, include_demo=False, limit=100)
    match = [r for r in public if r.get("building_name") == "Schema Alias Tower"]
    assert len(match) == 1
    assert match[0]["is_demo"] is False
    assert match[0]["status"] == "verified"


@pytest.mark.db
def test_imported_incentive_separate_from_demo(conn):
    admin_id = _ensure_admin(conn, f"csv-demo-{uuid4().hex[:8]}@example.com")
    demo_before = [r for r in list_incentives_ranked(conn, include_demo=True, limit=200) if r.get("is_demo")]
    validate_and_import_csv(conn, VALID_CSV, admin_user_id=admin_id, dry_run=False)

    real_only = list_incentives_ranked(conn, include_demo=False, limit=200)
    demo_in_real = [r for r in real_only if r.get("is_demo")]
    assert demo_in_real == []

    if demo_before:
        demo_only = list_incentives_ranked(conn, include_demo=True, limit=200)
        assert any(r.get("is_demo") for r in demo_only)


@pytest.mark.db
def test_dry_run_does_not_insert(conn):
    admin_id = _ensure_admin(conn, f"csv-dry-{uuid4().hex[:8]}@example.com")
    before = len(list_incentives_ranked(conn, include_demo=False, limit=200))
    result = validate_and_import_csv(conn, VALID_CSV, admin_user_id=admin_id, dry_run=True)
    assert result.created_count == 2
    assert result.error_count == 0
    after = len(list_incentives_ranked(conn, include_demo=False, limit=200))
    assert after == before


@pytest.mark.db
def test_admin_import_http_endpoint(conn, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    admin_email = f"csv-http-{uuid4().hex[:8]}@example.com"
    monkeypatch.setenv("ADMIN_EMAILS", admin_email)
    get_settings.cache_clear()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        reg = client.post(
            "/auth/register",
            json={"email": admin_email, "password": "testpassword123", "name": "CSV Admin"},
        )
        token = reg.json()["access_token"]
        csv_bytes = (
            "building_name,address,city,state,neighborhood,source_url,listed_rent,lease_months,free_months\n"
            "HTTP Import Tower,600 HTTP Ave,Reston,VA,Reston Town Center,https://leasing.import-test.invalid/http,2500,13,2\n"
        ).encode()
        r = client.post(
            "/admin/incentives/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("import.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["created_count"] == 1
        assert body["error_count"] == 0

        specials = client.get("/incentives?include_demo=false")
        assert specials.status_code == 200
        names = [x.get("building_name") for x in specials.json()]
        assert "HTTP Import Tower" in names

        search = client.get("/search?include_demo=false")
        assert search.status_code == 200
        search_names = [b.get("name") for b in search.json()]
        assert "HTTP Import Tower" in search_names
    finally:
        close_pool()
        get_settings.cache_clear()


def _ensure_admin(conn, email: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, name, is_admin)
            VALUES (%s, %s, true)
            ON CONFLICT (email) DO UPDATE SET is_admin = true
            RETURNING id
            """,
            (email, "CSV Admin"),
        )
        uid = cur.fetchone()[0]
    conn.commit()
    return uid
