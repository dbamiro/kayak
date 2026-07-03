"""Rate limit tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.rate_limit import check_rate_limit, reset_rate_limits_for_tests


def _fake_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_rate_limit_blocks_after_threshold():
    reset_rate_limits_for_tests()
    req = _fake_request()
    for _ in range(3):
        check_rate_limit(req, namespace="test", limit=3, window_seconds=60)
    with pytest.raises(HTTPException) as exc:
        check_rate_limit(req, namespace="test", limit=3, window_seconds=60)
    assert exc.value.status_code == 429


@pytest.mark.db
def test_register_rate_limit_http(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    monkeypatch.setenv("RATE_LIMIT_AUTH_REGISTER_PER_MINUTE", "2")
    get_settings.cache_clear()
    reset_rate_limits_for_tests()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        body = {"email": "rl@example.com", "password": "testpassword123"}
        assert client.post("/auth/register", json=body).status_code == 201
        body["email"] = "rl2@example.com"
        assert client.post("/auth/register", json=body).status_code == 201
        body["email"] = "rl3@example.com"
        assert client.post("/auth/register", json=body).status_code == 429
    finally:
        reset_rate_limits_for_tests()
        close_pool()
        get_settings.cache_clear()
