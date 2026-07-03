"""Simple in-memory rate limiting for auth and public submission endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from hashlib import sha256

from fastapi import HTTPException, Request, status

from app.config import get_settings

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)
_recent_submission_hashes: dict[str, float] = {}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def check_rate_limit(request: Request, *, namespace: str, limit: int, window_seconds: int = 60) -> None:
    """Raise 429 when client exceeds limit within window."""
    if limit <= 0:
        return
    key = f"{namespace}:{client_ip(request)}"
    now = time.monotonic()
    with _lock:
        bucket = _hits[key]
        bucket[:] = [t for t in bucket if now - t < window_seconds]
        if len(bucket) >= limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limit_exceeded",
            )
        bucket.append(now)


def check_auth_register_limit(request: Request) -> None:
    s = get_settings()
    check_rate_limit(
        request,
        namespace="auth:register",
        limit=s.rate_limit_auth_register_per_minute,
    )


def check_auth_login_limit(request: Request) -> None:
    s = get_settings()
    check_rate_limit(
        request,
        namespace="auth:login",
        limit=s.rate_limit_auth_login_per_minute,
    )


def check_incentive_submit_limit(request: Request) -> None:
    s = get_settings()
    check_rate_limit(
        request,
        namespace="incentives:submit",
        limit=s.rate_limit_incentive_submit_per_minute,
    )


def check_admin_api_limit(request: Request) -> None:
    s = get_settings()
    check_rate_limit(
        request,
        namespace="admin:api",
        limit=s.rate_limit_admin_per_minute,
    )


def check_duplicate_submission(request: Request, raw_text: str, *, window_seconds: int = 600) -> None:
    """Block identical submission text from the same IP within window."""
    from app.abuse_validation import normalize_text

    normalized = normalize_text(raw_text)
    digest = sha256(normalized.encode()).hexdigest()[:16]
    key = f"{client_ip(request)}:{digest}"
    now = time.monotonic()
    with _lock:
        expired = [k for k, t in _recent_submission_hashes.items() if now - t >= window_seconds]
        for k in expired:
            del _recent_submission_hashes[k]
        if key in _recent_submission_hashes:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="duplicate_submission",
            )
        _recent_submission_hashes[key] = now


def reset_rate_limits_for_tests() -> None:
    """Clear buckets between tests."""
    with _lock:
        _hits.clear()
        _recent_submission_hashes.clear()
