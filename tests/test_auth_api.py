"""Auth API tests: JWT helpers (no DB) and register/login/me when DATABASE_URL is set."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import jwt_tokens as jwt_mod
from app.config import get_settings
from app.main import app


def test_access_token_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-key-32chars!")
    get_settings.cache_clear()
    try:
        from uuid import uuid4

        uid = uuid4()
        tok = jwt_mod.create_access_token(uid, email="user@example.com")
        payload = jwt_mod.decode_access_token(tok)
        assert payload["sub"] == str(uid)
        assert payload["email"] == "user@example.com"
        assert payload["type"] == "access"
    finally:
        get_settings.cache_clear()


def test_auth_me_without_credentials() -> None:
    client = TestClient(app)
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_auth_me_with_bad_bearer() -> None:
    client = TestClient(app)
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_me_entitlements_without_credentials() -> None:
    client = TestClient(app)
    r = client.get("/me/entitlements")
    assert r.status_code == 401


@pytest.mark.db
def test_register_login_me_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requires Postgres with schema including users.password_hash and refresh_tokens."""
    monkeypatch.setenv("JWT_SECRET", "integration-test-jwt-secret-32chars!")
    get_settings.cache_clear()
    try:
        from app.db import close_pool

        close_pool()
        client = TestClient(app)
        email = f"auth-test-{uuid.uuid4().hex[:10]}@example.com"
        pw = "testpassword123"

        reg = client.post("/auth/register", json={"email": email, "password": pw, "name": "Auth Test"})
        assert reg.status_code == 201, reg.text
        access = reg.json()["access_token"]

        me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200
        assert me.json()["email"] == email

        ent = client.get("/me/entitlements", headers={"Authorization": f"Bearer {access}"})
        assert ent.status_code == 200
        body = ent.json()
        assert body["user"]["email"] == email
        assert isinstance(body.get("feature_flags"), dict)

        login = client.post("/auth/login", json={"email": email, "password": pw})
        assert login.status_code == 200
        assert login.json()["user"]["email"] == email
    finally:
        close_pool()
        get_settings.cache_clear()
