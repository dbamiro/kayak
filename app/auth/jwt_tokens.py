"""JWT access tokens and opaque refresh tokens (hashed at rest)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt

from app.config import get_settings


def _secret() -> str:
    s = get_settings().jwt_secret
    if not s or s == "change-me-in-production":
        # Dev-only weak default; production must set JWT_SECRET
        return "dev-insecure-jwt-secret-change-me"
    return s


def create_access_token(user_id: UUID, *, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=["HS256"])


def new_refresh_token_value() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
