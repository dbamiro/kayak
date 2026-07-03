"""Resolve current user from JWT Bearer or optional mock headers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row

from app.auth.jwt_tokens import decode_access_token
from app.config import get_settings
from app.db import get_pool

security = HTTPBearer(auto_error=False)


@dataclass
class UserPrincipal:
    id: UUID
    email: str
    name: str | None
    is_admin: bool


def _load_user(user_id: UUID) -> UserPrincipal | None:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, email, name, is_admin FROM users WHERE id = %s",
                (str(user_id),),
            )
            row = cur.fetchone()
    if not row:
        return None
    return UserPrincipal(
        id=UUID(str(row["id"])),
        email=row["email"],
        name=row.get("name"),
        is_admin=bool(row.get("is_admin")),
    )


def _admin_by_email(email: str) -> bool:
    settings = get_settings()
    admins = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    return email.lower() in admins


def get_user_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> UserPrincipal:
    settings = get_settings()

    if creds and creds.scheme.lower() == "bearer":
        try:
            payload = decode_access_token(creds.credentials)
            if payload.get("type") != "access":
                raise ValueError("wrong token type")
            uid = UUID(str(payload["sub"]))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from exc
        user = _load_user(uid)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_not_found")
        is_adm = user.is_admin or _admin_by_email(user.email)
        return UserPrincipal(id=user.id, email=user.email, name=user.name, is_admin=is_adm)

    if settings.mock_auth_mode and x_user_id:
        try:
            uid = UUID(x_user_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad_x_user_id") from exc
        user = _load_user(uid)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_not_found")
        is_adm = user.is_admin or _admin_by_email(user.email)
        return UserPrincipal(id=user.id, email=user.email, name=user.name, is_admin=is_adm)

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "authentication_required",
    )


def get_user_principal_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> UserPrincipal | None:
    settings = get_settings()
    if creds and creds.scheme.lower() == "bearer":
        try:
            payload = decode_access_token(creds.credentials)
            if payload.get("type") != "access":
                raise ValueError("wrong token type")
            uid = UUID(str(payload["sub"]))
        except Exception:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")
        user = _load_user(uid)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_not_found")
        is_adm = user.is_admin or _admin_by_email(user.email)
        return UserPrincipal(id=user.id, email=user.email, name=user.name, is_admin=is_adm)
    if settings.mock_auth_mode and x_user_id:
        try:
            uid = UUID(x_user_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad_x_user_id") from exc
        user = _load_user(uid)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_not_found")
        is_adm = user.is_admin or _admin_by_email(user.email)
        return UserPrincipal(id=user.id, email=user.email, name=user.name, is_admin=is_adm)
    return None


CurrentUser = Annotated[UserPrincipal, Depends(get_user_principal)]
OptionalUser = Annotated[UserPrincipal | None, Depends(get_user_principal_optional)]


def require_admin(user: UserPrincipal = Depends(get_user_principal)) -> UserPrincipal:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin_only")
    return user


AdminUser = Annotated[UserPrincipal, Depends(require_admin)]
