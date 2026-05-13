"""Effective rent and all-in monthly cost calculations."""

from decimal import Decimal
from typing import Any


def _monthly_equiv_weeks_free(base_rent: Decimal, weeks: int) -> Decimal:
    # PLACEHOLDER: assumes ~4.33 weeks per month for conversion
    weeks_dec = Decimal(str(weeks))
    return base_rent * (weeks_dec / Decimal("4.33"))


def amortized_concession_monthly(concession: dict[str, Any], base_rent: Decimal, lease_months: int) -> Decimal:
    """
    PLACEHOLDER heuristics for common concession shapes.
    Extend per property CMS when you add site-specific parsers.
    """
    if not concession:
        return Decimal("0")
    ctype = concession.get("type")
    lm = max(lease_months, 1)

    if ctype == "one_time":
        amt = Decimal(str(concession.get("amount", 0)))
        return amt / Decimal(lm)

    if ctype == "percent_off":
        pct = Decimal(str(concession.get("percent", 0))) / Decimal("100")
        months = int(concession.get("months", 0))
        discount_total = base_rent * pct * Decimal(months)
        return discount_total / Decimal(lm)

    if ctype == "weeks_free":
        weeks = int(concession.get("weeks", 0))
        equiv = _monthly_equiv_weeks_free(base_rent, weeks)
        return equiv / Decimal(lm)

    # PLACEHOLDER: unknown structured concession — treat as zero until parser fills type
    return Decimal("0")


def sum_monthly_fees(fees: dict[str, Any] | None) -> Decimal:
    """Sums numeric monthly fee components (admin, amenity, pet, parking, garage, etc.)."""
    if not fees:
        return Decimal("0")
    total = Decimal("0")
    for _key, val in fees.items():
        try:
            total += Decimal(str(val))
        except Exception:
            continue
    return total


def compute_effective_rent(
    base_rent_monthly: Decimal,
    lease_term_months: int,
    concessions: dict[str, Any] | None,
) -> Decimal:
    reduction = amortized_concession_monthly(concessions or {}, base_rent_monthly, lease_term_months)
    return base_rent_monthly - reduction


def compute_all_in_monthly(
    effective_rent: Decimal,
    fees: dict[str, Any] | None,
    utilities_estimate: Decimal | None,
) -> Decimal:
    fees_sum = sum_monthly_fees(fees)
    utils_ = utilities_estimate or Decimal("0")
    return effective_rent + fees_sum + utils_
