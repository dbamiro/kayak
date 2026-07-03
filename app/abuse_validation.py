"""Input validation helpers for abuse protection."""

from __future__ import annotations

import re
import unicodedata

from fastapi import HTTPException

# Obvious spam / empty-ish patterns
_REPEATED_CHAR = re.compile(r"(.)\1{9,}")
_URL_LIKE = re.compile(r"^https?://", re.I)


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split()).lower()


def validate_submission_text(raw_text: str, *, field: str = "raw_special_text") -> str:
    """Reject empty-ish, too-short, or obvious spam text."""
    cleaned = raw_text.strip()
    if len(cleaned) < 10:
        raise HTTPException(
            422,
            detail=f"{field}_too_short",
        )
    if _REPEATED_CHAR.search(cleaned):
        raise HTTPException(
            422,
            detail=f"{field}_looks_like_spam",
        )
    alpha = sum(1 for c in cleaned if c.isalpha())
    if alpha < 5:
        raise HTTPException(
            422,
            detail=f"{field}_insufficient_content",
        )
    return cleaned


def validate_optional_url(value: str | None, *, field: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    v = str(value).strip()
    if len(v) > 2048:
        raise HTTPException(422, detail=f"{field}_too_long")
    if not _URL_LIKE.match(v):
        raise HTTPException(422, detail=f"{field}_must_be_url")
    return v


def require_building_reference(*, building_id, building_name: str | None) -> None:
    has_id = building_id is not None
    has_name = bool(building_name and building_name.strip())
    if not has_id and not has_name:
        raise HTTPException(
            422,
            detail="building_name_or_building_id_required",
        )
