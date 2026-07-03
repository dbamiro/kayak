"""Email/password auth: register, login, JWT access + opaque refresh tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field

from app.auth.jwt_tokens import create_access_token, hash_refresh_token, new_refresh_token_value
from app.auth.passwords import hash_password, verify_password
from app.config import get_settings
from app.deps import ConnDep
from app.deps_auth import CurrentUser
from app.rate_limit import check_auth_login_limit, check_auth_register_limit

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=120)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RefreshBody(BaseModel):
    refresh_token: str


class LogoutBody(BaseModel):
    refresh_token: str


def _safe_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "name": row.get("name"),
        "email_verified": bool(row.get("email_verified", False)),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _issue_tokens(conn, *, user_id: UUID, email: str) -> dict[str, Any]:
    settings = get_settings()
    access = create_access_token(user_id, email=email)
    raw_refresh = new_refresh_token_value()
    rhash = hash_refresh_token(raw_refresh)
    exp = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_days)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (str(user_id), rhash, exp),
        )
    conn.commit()
    return {
        "access_token": access,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.jwt_expires_minutes * 60,
    }


@router.post("/register", status_code=201)
def register(conn: ConnDep, body: RegisterBody, request: Request) -> dict[str, Any]:
    check_auth_register_limit(request)
    email = body.email.lower().strip()
    ph = hash_password(body.password)
    with conn.cursor(row_factory=dict_row) as cur:
        try:
            cur.execute(
                """
                INSERT INTO users (email, name, password_hash)
                VALUES (%(e)s, %(n)s, %(p)s)
                RETURNING id, email, name, email_verified, created_at
                """,
                {"e": email, "n": body.name, "p": ph},
            )
            row = cur.fetchone()
        except pg_errors.UniqueViolation as exc:
            conn.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "email_already_registered") from exc
    conn.commit()
    assert row is not None
    uid = UUID(str(row["id"]))
    tokens = _issue_tokens(conn, user_id=uid, email=row["email"])
    return {"user": _safe_user(dict(row)), **tokens}


@router.post("/login")
def login(conn: ConnDep, body: LoginBody, request: Request) -> dict[str, Any]:
    check_auth_login_limit(request)
    email = body.email.lower().strip()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, email, name, password_hash, email_verified, created_at
            FROM users WHERE email = %s
            """,
            (email,),
        )
        row = cur.fetchone()
    if not row or not verify_password(body.password, row.get("password_hash")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    uid = UUID(str(row["id"]))
    tokens = _issue_tokens(conn, user_id=uid, email=row["email"])
    return {"user": _safe_user(dict(row)), **tokens}


@router.get("/me")
def me(user: CurrentUser, conn: ConnDep) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, email, name, email_verified, is_admin, created_at
            FROM users WHERE id = %s
            """,
            (str(user.id),),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_not_found")
    out = _safe_user(dict(row))
    out["is_admin"] = bool(row.get("is_admin")) or user.is_admin
    return out


@router.post("/refresh")
def refresh_token(conn: ConnDep, body: RefreshBody) -> dict[str, Any]:
    h = hash_refresh_token(body.refresh_token)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, user_id, expires_at, revoked_at
            FROM refresh_tokens
            WHERE token_hash = %s
            """,
            (h,),
        )
        tok = cur.fetchone()
    if not tok or tok.get("revoked_at"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_refresh_token")
    exp = tok["expires_at"]
    if exp and exp < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh_token_expired")

    uid = UUID(str(tok["user_id"]))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT email FROM users WHERE id = %s", (str(uid),))
        u = cur.fetchone()
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_not_found")

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET revoked_at = now() WHERE id = %s",
            (str(tok["id"]),),
        )
    conn.commit()
    return _issue_tokens(conn, user_id=uid, email=u["email"])


@router.post("/logout")
def logout(conn: ConnDep, body: LogoutBody) -> dict[str, bool]:
    h = hash_refresh_token(body.refresh_token)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE refresh_tokens
            SET revoked_at = now()
            WHERE token_hash = %s AND revoked_at IS NULL
            """,
            (h,),
        )
    conn.commit()
    return {"ok": True}
