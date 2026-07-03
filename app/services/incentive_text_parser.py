"""Parse concession / move-in special text into structured incentive fields."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.incentive_calculator import WEEKS_PER_MONTH, weeks_free_to_months

WORD_NUMBERS: dict[str, float] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "ten": 10,
    "twelve": 12,
}


@dataclass
class ParsedIncentive:
    incentive_type: str
    free_months: float | None = None
    weeks_free: float | None = None
    waived_fee_amount: int | None = None
    gift_card_amount: int | None = None
    parking_discount_monthly: int | None = None
    custom_credit_amount: int | None = None
    confidence_score: float = 0.5
    raw_text: str = ""


def _word_or_digit(s: str) -> float | None:
    s = s.strip().lower()
    if s in WORD_NUMBERS:
        return WORD_NUMBERS[s]
    try:
        return float(s)
    except ValueError:
        return None


def _parse_money(raw: str) -> int:
    return int(raw.replace(",", ""))


def parse_incentive_text(raw_text: str) -> ParsedIncentive:
    """Detect free months/weeks, waived fees, credits, parking from marketing copy."""
    text = (raw_text or "").strip()
    lower = text.lower()
    if not text:
        return ParsedIncentive(incentive_type="unknown", confidence_score=0.0, raw_text=text)

    # Weeks free (2, 4, 6, 8, 10, 12)
    wm = re.search(
        r"(?:up to\s+)?(\d+(?:\.\d+)?|two|four|six|eight|ten|twelve)\s+weeks?\s+free",
        lower,
    )
    if wm:
        w = _word_or_digit(wm.group(1) or "")
        if w is not None:
            return ParsedIncentive(
                incentive_type="free_weeks",
                weeks_free=w,
                free_months=weeks_free_to_months(w),
                confidence_score=0.88,
                raw_text=text,
            )

    # Decimal / word months free, including "up to N months"
    mm = re.search(
        r"(?:up to\s+)?(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|ten|twelve)"
        r"\s+months?\s+free",
        lower,
    )
    if mm:
        val = _word_or_digit(mm.group(1) or "")
        if val is not None:
            return ParsedIncentive(
                incentive_type="free_months",
                free_months=val,
                confidence_score=0.9 if "up to" not in lower[: mm.start() + 10] else 0.85,
                raw_text=text,
            )

    # Singular "1 month free" / "one month free"
    if re.search(r"(?:1|one)\s+month\s+free", lower):
        return ParsedIncentive(
            incentive_type="free_months", free_months=1.0, confidence_score=0.92, raw_text=text
        )

    # Rent / move-in credit
    credit = re.search(
        r"\$\s*([\d,]+)\s*(?:rent|move-in)\s*credit|\$\s*([\d,]+)\s*off(?:\s+your\s+first)?",
        lower,
    )
    if credit or "rent credit" in lower or "move-in credit" in lower:
        raw_amt = credit.group(1) or credit.group(2) if credit else None
        amt = _parse_money(raw_amt) if raw_amt else 500
        return ParsedIncentive(
            incentive_type="rent_credit",
            custom_credit_amount=amt,
            confidence_score=0.82 if raw_amt else 0.65,
            raw_text=text,
        )

    if re.search(r"look[- ]and[- ]lease", lower):
        return ParsedIncentive(
            incentive_type="look_and_lease",
            custom_credit_amount=500,
            confidence_score=0.6,
            raw_text=text,
        )

    if re.search(r"waived\s+admin(?:istrative)?\s+fee", lower):
        amt = _money_after(lower, r"admin")
        return ParsedIncentive(
            incentive_type="waived_admin_fee",
            waived_fee_amount=amt or 500,
            confidence_score=0.8 if amt else 0.65,
            raw_text=text,
        )

    if re.search(r"waived\s+application\s+fee", lower):
        amt = _money_after(lower, r"application")
        return ParsedIncentive(
            incentive_type="waived_application_fee",
            waived_fee_amount=amt or 75,
            confidence_score=0.8 if amt else 0.65,
            raw_text=text,
        )

    gm = re.search(r"\$\s*([\d,]+)\s*(?:gift\s*card|visa|amex)", lower)
    if gm or "gift card" in lower:
        amt = _parse_money(gm.group(1)) if gm else 500
        return ParsedIncentive(
            incentive_type="gift_card",
            gift_card_amount=amt,
            confidence_score=0.82 if gm else 0.6,
            raw_text=text,
        )

    if "free parking" in lower or "complimentary parking" in lower:
        pm = re.search(r"\$\s*([\d,]+)\s*(?:/|\s*per\s*)?month", lower)
        months_match = re.search(r"(\d+)\s+months?", lower)
        monthly = _parse_money(pm.group(1)) if pm else 150
        if months_match and not pm:
            monthly = 150
        return ParsedIncentive(
            incentive_type="free_parking",
            parking_discount_monthly=monthly,
            confidence_score=0.75,
            raw_text=text,
        )

    if "reduced deposit" in lower or "lower deposit" in lower:
        dm = re.search(r"\$\s*([\d,]+)", lower)
        return ParsedIncentive(
            incentive_type="reduced_deposit",
            waived_fee_amount=_parse_money(dm.group(1)) if dm else 500,
            confidence_score=0.7,
            raw_text=text,
        )

    return ParsedIncentive(incentive_type="unknown", raw_text=text, confidence_score=0.4)


def _money_after(lower: str, keyword: str) -> int | None:
    m = re.search(rf"\$\s*([\d,]+)[^$]{{0,40}}{keyword}|{keyword}[^$]{{0,40}}\$\s*([\d,]+)", lower)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    return _parse_money(raw) if raw else None


def format_incentive_headline(row: dict) -> str:
    """Human-readable special label for API/cards (not limited to months free)."""
    raw = (row.get("raw_text") or "").lower()
    itype = row.get("incentive_type") or ""

    if row.get("weeks_free") is not None or (
        itype == "free_weeks" and re.search(r"\d+\s*weeks?", raw)
    ):
        wm = re.search(r"(\d+(?:\.\d+)?)\s*weeks?", raw)
        if wm:
            w = float(wm.group(1))
            return f"{w:g} weeks free" if w != 1 else "1 week free"

    fm = row.get("free_months")
    if fm is not None and float(fm) > 0:
        f = float(fm)
        if abs(f - round(f)) < 0.05:
            n = int(round(f))
            return f"{n} month{'s' if n != 1 else ''} free"
        return f"{f:.1f} months free"

    if itype == "waived_admin_fee" or "waived admin" in raw:
        return "Waived admin fee"
    if itype == "waived_application_fee":
        return "Waived application fee"
    if row.get("gift_card_amount"):
        return f"${int(row['gift_card_amount']):,} gift card"
    if row.get("custom_credit_amount"):
        return f"${int(row['custom_credit_amount']):,} rent credit"
    if itype == "free_parking" or "free parking" in raw:
        return "Free parking"
    if itype == "look_and_lease":
        return "Look & lease special"
    if row.get("raw_text"):
        return str(row["raw_text"])[:120]
    return itype.replace("_", " ") or "Move-in special"
