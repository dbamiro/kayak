"""Effective rent and total savings from move-in specials."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

WEEKS_PER_MONTH = 4.333


@dataclass(frozen=True)
class IncentiveCalculation:
    gross_rent_total: int
    concession_value: int
    fee_adjustments: int
    total_savings: int
    effective_rent: int
    all_in_effective_rent: int
    discount_percent: float
    free_months_applied: float


def _i(n: int | float | Decimal | None) -> int:
    if n is None:
        return 0
    return int(Decimal(str(n)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def weeks_free_to_months(weeks: float) -> float:
    """Convert weeks-free specials to fractional months."""
    return weeks / WEEKS_PER_MONTH


def calculate_effective_rent(
    listed_rent: int,
    lease_term_months: int,
    free_months: float | Decimal = 0,
    *,
    recurring_fee_monthly: int = 0,
    one_time_fee: int = 0,
    waived_fee_amount: int = 0,
    gift_card_amount: int = 0,
    parking_discount_monthly: int = 0,
    custom_credit_amount: int = 0,
    clamp_free_months: bool = True,
) -> IncentiveCalculation:
    """
  Compute gross lease cost, concession value, and effective monthly rent.

  Example: $2,400/mo, 16-month lease, 4 months free → effective $1,800/mo.
  """
    if lease_term_months <= 0:
        raise ValueError("lease_term_months must be positive")
    rent = _i(listed_rent)
    if rent <= 0:
        raise ValueError("listed_rent must be positive")

    term = lease_term_months
    fm = float(free_months or 0)
    if fm > term:
        if clamp_free_months:
            fm = float(term)
        else:
            raise ValueError("free_months cannot exceed lease_term_months")

    gross_rent_total = rent * term
    free_rent_value = _i(Decimal(str(rent)) * Decimal(str(fm)))
    fee_adjustments = (
        _i(waived_fee_amount)
        + _i(gift_card_amount)
        + _i(custom_credit_amount)
        + _i(parking_discount_monthly) * term
    )
    total_savings = free_rent_value + fee_adjustments
    if total_savings < 0:
        total_savings = 0

    net_rent = max(0, gross_rent_total - total_savings)
    effective_rent = _i(Decimal(net_rent) / Decimal(term)) if term else 0
    all_in_effective_rent = effective_rent + _i(recurring_fee_monthly) + (
        _i(one_time_fee) // term if term else 0
    )
    discount_percent = (
        round((total_savings / gross_rent_total) * 100, 2) if gross_rent_total > 0 else 0.0
    )

    return IncentiveCalculation(
        gross_rent_total=gross_rent_total,
        concession_value=free_rent_value,
        fee_adjustments=fee_adjustments,
        total_savings=total_savings,
        effective_rent=effective_rent,
        all_in_effective_rent=all_in_effective_rent,
        discount_percent=discount_percent,
        free_months_applied=fm,
    )
