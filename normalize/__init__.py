"""Normalization helpers: currency strings → decimals, bedroom labels, etc."""

from decimal import Decimal, InvalidOperation
import re


_NON_DIGIT = re.compile(r"[^\d.\-]")


def parse_money(value: str | None) -> Decimal | None:
    """PLACEHOLDER: extend for locale-specific formats ($1,234.56)."""
    if value is None or not str(value).strip():
        return None
    cleaned = _NON_DIGIT.sub("", str(value))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_bedrooms(label: str | None) -> Decimal | None:
    """Maps 'Studio', '1 BR', '2bd' → numeric bedrooms (studio → 0)."""
    if label is None:
        return None
    s = label.strip().lower()
    if s.startswith("studio") or s == "efficiency":
        return Decimal("0")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            return None
    return None


def clamp_int(n: float | int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(n))))
