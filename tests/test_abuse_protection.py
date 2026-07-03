"""Abuse protection: rate limits, validation, admin access."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.abuse_validation import validate_submission_text
from app.config import get_settings
from app.main import app
from app.rate_limit import check_duplicate_submission, reset_rate_limits_for_tests
from fastapi import HTTPException


def test_validate_submission_text_rejects_spam():
    with pytest.raises(HTTPException) as exc:
        validate_submission_text("aaaaaaaaaa")
    assert exc.value.status_code == 422
    assert "spam" in str(exc.value.detail).lower() or "insufficient" in str(exc.value.detail).lower()


def test_validate_submission_text_accepts_real_copy():
    text = validate_submission_text("Two months free on 14-month lease at the leasing office")
    assert "two months free" in text.lower()


def test_duplicate_submission_blocked():
    reset_rate_limits_for_tests()
    from fastapi import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/incentives/submit",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    text = "Two months free on 14-month lease special"
    check_duplicate_submission(req, text)
    with pytest.raises(HTTPException) as exc:
        check_duplicate_submission(req, text)
    assert exc.value.status_code == 429
    assert exc.value.detail == "duplicate_submission"


@pytest.mark.db
def test_submit_requires_building(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    get_settings.cache_clear()
    reset_rate_limits_for_tests()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        r = client.post(
            "/incentives/submit",
            json={
                "raw_special_text": "Two months free on 14-month lease at front desk",
                "rent": 2400,
                "lease_term_months": 14,
            },
        )
        assert r.status_code == 422
    finally:
        reset_rate_limits_for_tests()
        close_pool()
        get_settings.cache_clear()


@pytest.mark.db
def test_submit_rate_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    monkeypatch.setenv("RATE_LIMIT_INCENTIVE_SUBMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    reset_rate_limits_for_tests()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        body = {
            "building_name": "Kayak Test Alpha",
            "city": "Washington",
            "raw_special_text": "Two months free on 14-month lease verified at desk",
            "rent": 2400,
            "lease_term_months": 14,
        }
        assert client.post("/incentives/submit", json=body).status_code == 201
        body["raw_special_text"] = "Three weeks free on 12-month lease at front desk"
        assert client.post("/incentives/submit", json=body).status_code == 201
        body["raw_special_text"] = "One month free on 13-month lease at front desk"
        assert client.post("/incentives/submit", json=body).status_code == 429
    finally:
        reset_rate_limits_for_tests()
        close_pool()
        get_settings.cache_clear()


@pytest.mark.db
def test_login_rate_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    monkeypatch.setenv("RATE_LIMIT_AUTH_LOGIN_PER_MINUTE", "3")
    get_settings.cache_clear()
    reset_rate_limits_for_tests()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        body = {"email": "nobody@example.com", "password": "wrongpassword1"}
        for _ in range(3):
            assert client.post("/auth/login", json=body).status_code == 401
        assert client.post("/auth/login", json=body).status_code == 429
    finally:
        reset_rate_limits_for_tests()
        close_pool()
        get_settings.cache_clear()
