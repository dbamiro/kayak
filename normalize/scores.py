"""Building-level leasing pressure and renter negotiation scores (0–100)."""

from decimal import Decimal
from typing import Any

from normalize import clamp_int
from normalize.rents import sum_monthly_fees


def _concession_intensity(base_rent: Decimal, concessions: dict[str, Any] | None) -> float:
    """Rough 0–1 score from structured concessions (PLACEHOLDER weights)."""
    if not concessions:
        return 0.0
    ctype = concessions.get("type")
    if ctype == "one_time":
        amt = float(Decimal(str(concessions.get("amount", 0))))
        return min(1.0, (amt / max(float(base_rent), 1.0)) / 3.0)
    if ctype == "percent_off":
        pct = float(concessions.get("percent", 0)) / 100.0
        months = float(concessions.get("months", 0))
        return min(1.0, pct * months / 12.0)
    if ctype == "weeks_free":
        w = float(concessions.get("weeks", 0))
        return min(1.0, w / 8.0)
    return 0.2  # PLACEHOLDER: unknown concession present → mild signal


def _fee_burden_ratio(base_rent: Decimal, fees: dict[str, Any] | None) -> float:
    fees_sum = float(sum_monthly_fees(fees))
    br = float(base_rent) if base_rent > 0 else 1.0
    return min(1.0, fees_sum / br)


def leasing_pressure_score(
    base_rent_monthly: Decimal,
    concessions: dict[str, Any] | None,
    fees: dict[str, Any] | None,
    availability_status: str | None,
    prior_base_rent_monthly: Decimal | None,
) -> int:
    """
    Higher score ⇒ stronger landlord incentive to fill units at this snapshot (renter-favorable market signal).

    PLACEHOLDER composition — tune with real DMV seasonality and vacancy proxies later.
    """
    ci = _concession_intensity(base_rent_monthly, concessions)
    fee_ratio = _fee_burden_ratio(base_rent_monthly, fees)

    avail = (availability_status or "").lower()
    avail_pts = 15.0
    if avail in ("immediate", "available now", "available"):
        avail_pts = 25.0
    elif not avail:
        avail_pts = 12.0

    trend_pts = 0.0
    if prior_base_rent_monthly is not None and prior_base_rent_monthly > base_rent_monthly:
        drop_ratio = float((prior_base_rent_monthly - base_rent_monthly) / prior_base_rent_monthly)
        trend_pts = min(20.0, drop_ratio * 100.0)

    raw = ci * 35.0 + (1.0 - fee_ratio) * 10.0 + avail_pts + trend_pts
    return clamp_int(raw, 0, 100)


def negotiation_score(
    leasing_pressure: int,
    base_rent_monthly: Decimal,
    concessions: dict[str, Any] | None,
    fees: dict[str, Any] | None,
) -> int:
    """
    Higher score ⇒ relatively better expected leverage for the renter on negotiable terms.

    Uses leasing_pressure as anchor and adjusts for concession richness minus fee drag.
    PLACEHOLDER — extend with DOM, inventory counts, and seasonal indices when available.
    """
    ci = _concession_intensity(base_rent_monthly, concessions)
    fee_ratio = _fee_burden_ratio(base_rent_monthly, fees)

    raw = (
        leasing_pressure * 0.55
        + ci * 30.0
        + (1.0 - fee_ratio) * 15.0
    )
    return clamp_int(raw, 0, 100)
