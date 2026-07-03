"""Typed API models shared by routers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SearchHit(BaseModel):
    building_id: UUID
    name: str
    city: str
    neighborhood: str | None = None
    dmv_area: str
    listing_id: UUID
    bedrooms: Decimal | None
    base_rent_monthly: Decimal | None = None
    effective_rent_monthly: Decimal | None
    all_in_monthly: Decimal | None
    leasing_pressure_score: int | None
    negotiation_score: int | None
    snapshot_at: datetime
    has_concession: bool = False
    has_fees: bool = False
    deal_signal: str = "fair"
    # Best active move-in incentive for this building (optional; backward-compatible)
    best_incentive_id: UUID | None = None
    incentive_type: str | None = None
    raw_text: str | None = None
    free_months: float | None = None
    lease_term_months: int | None = None
    listed_rent: int | None = None
    estimated_savings: int | None = None
    effective_rent: int | None = None
    all_in_effective_rent: int | None = None
    discount_percent: float | None = None
    confidence_score: float | None = None
    verified_at: datetime | None = None
    incentive_is_demo: bool | None = None


class BuildingDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    city: str
    state: str
    postal_code: str | None
    neighborhood: str | None
    dmv_area: str
    property_url: str
    latitude: float | None = None
    longitude: float | None = None


class ListingQuote(BaseModel):
    listing_id: UUID
    unit_label: str | None
    floorplan_name: str | None
    bedrooms: Decimal | None
    bathrooms: Decimal | None
    sqft: int | None
    snapshot_at: datetime
    base_rent_monthly: Decimal | None
    effective_rent_monthly: Decimal | None
    all_in_monthly: Decimal | None
    leasing_pressure_score: int | None
    negotiation_score: int | None
    concessions: dict[str, Any] = Field(default_factory=dict)
    fees: dict[str, Any] = Field(default_factory=dict)


class SnapshotPoint(BaseModel):
    captured_at: datetime
    base_rent_monthly: Decimal | None
    effective_rent_monthly: Decimal | None
    all_in_monthly: Decimal | None
    leasing_pressure_score: int | None
    negotiation_score: int | None


class CompareRequest(BaseModel):
    building_ids: list[UUID] = Field(min_length=2)
    bedrooms_min: Decimal | None = None


class CompareRow(BaseModel):
    building_id: UUID
    building_name: str
    city: str
    dmv_area: str
    listing_id: UUID
    bedrooms: Decimal | None
    effective_rent_monthly: Decimal | None
    all_in_monthly: Decimal | None
    leasing_pressure_score: int | None = None
    negotiation_score: int | None = None


class AlertCreate(BaseModel):
    name: str | None = None
    email: str | None = None
    label: str | None = None
    criteria: dict[str, Any]
    alert_type: str = "general"


class AlertPatch(BaseModel):
    name: str | None = None
    label: str | None = None
    criteria: dict[str, Any] | None = None
    alert_type: str | None = None
    active: bool | None = None


class AlertOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    email: str | None = None
    label: str | None = None
    name: str | None = None
    alert_type: str = "general"
    criteria: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime | None = None


class IncentiveCalculationOut(BaseModel):
    gross_rent_total: int
    concession_value: int
    fee_adjustments: int
    total_savings: int
    effective_rent: int
    all_in_effective_rent: int
    discount_percent: float


class IncentiveCalculateBody(BaseModel):
    listed_rent: int = Field(gt=0)
    lease_term_months: int = Field(gt=0, le=60)
    free_months: float = Field(ge=0, default=0)
    recurring_fee_monthly: int = Field(ge=0, default=0)
    one_time_fee: int = Field(ge=0, default=0)
    waived_fee_amount: int = Field(ge=0, default=0)
    gift_card_amount: int = Field(ge=0, default=0)
    parking_discount_monthly: int = Field(ge=0, default=0)
    custom_credit_amount: int = Field(ge=0, default=0)


class IncentiveParseBody(BaseModel):
    raw_text: str = Field(min_length=3)
    listed_rent: int | None = Field(default=None, gt=0)
    lease_term_months: int | None = Field(default=None, gt=0, le=60)


class IncentiveParseOut(BaseModel):
    parsed: dict[str, Any]
    calculation: IncentiveCalculationOut | None = None


class IncentiveSubmitBody(BaseModel):
    building_name: str | None = Field(default=None, max_length=200)
    building_id: UUID | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    screenshot_url: str | None = Field(default=None, max_length=2048)
    raw_special_text: str = Field(min_length=10, max_length=4000)
    rent: int | None = Field(default=None, gt=0, le=50000)
    lease_term_months: int | None = Field(default=12, gt=0, le=60)
    city: str | None = Field(default=None, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=100)
    applies_to: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_building(self) -> IncentiveSubmitBody:
        if not self.building_id and not (self.building_name and self.building_name.strip()):
            raise ValueError("building_name_or_building_id_required")
        return self


class AdminIncentiveCreate(BaseModel):
    building_id: UUID | None = None
    building_name: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    source_url: str | None = None
    raw_text: str = Field(min_length=3)
    listed_rent: int = Field(gt=0)
    lease_term_months: int = Field(gt=0, le=60)
    free_months: float | None = Field(default=None, ge=0)
    waived_fee_amount: int | None = Field(default=None, ge=0)
    gift_card_amount: int | None = Field(default=None, ge=0)
    custom_credit_amount: int | None = Field(default=None, ge=0)
    recurring_fee_monthly: int | None = Field(default=None, ge=0)
    applies_to: str | None = None
    expires_at: datetime | None = None
    verification_method: str | None = "leasing_office_verified"


class AdminIncentiveUpdate(BaseModel):
    building_id: UUID | None = None
    raw_text: str | None = Field(default=None, min_length=3)
    listed_rent: int | None = Field(default=None, gt=0)
    lease_term_months: int | None = Field(default=None, gt=0, le=60)
    free_months: float | None = Field(default=None, ge=0)
    waived_fee_amount: int | None = Field(default=None, ge=0)
    gift_card_amount: int | None = Field(default=None, ge=0)
    custom_credit_amount: int | None = Field(default=None, ge=0)
    parking_discount_monthly: int | None = Field(default=None, ge=0)
    incentive_type: str | None = None
    applies_to: str | None = None
    source_url: str | None = None
    expires_at: datetime | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    reparse_raw_text: bool = False


class AdminIncentiveRejectBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AdminIncentiveImportRowError(BaseModel):
    row: int
    field: str | None = None
    message: str


class AdminIncentiveImportResult(BaseModel):
    dry_run: bool = False
    created_count: int = 0
    error_count: int = 0
    errors: list[AdminIncentiveImportRowError] = Field(default_factory=list)
    created_incentive_ids: list[UUID] = Field(default_factory=list)


class IncentiveCardOut(BaseModel):
    id: UUID
    building_id: UUID | None = None
    building_name: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    dmv_area: str | None = None
    incentive_type: str
    free_months: float | None = None
    lease_term_months: int | None = None
    listed_rent: int | None = None
    raw_text: str | None = None
    special_summary: str | None = None
    is_demo: bool = False
    status: str | None = None
    capture_method: str | None = None
    verification_method: str | None = None
    verified_at: datetime | None = None
    reviewed_at: datetime | None = None
    submitted_by_user_id: UUID | None = None
    reviewed_by_user_id: UUID | None = None
    submitted_by_email: str | None = None
    reviewed_by_email: str | None = None
    confidence_score: float | None = None
    gross_rent_total: int | None = None
    total_savings: int | None = None
    effective_rent: int | None = None
    all_in_effective_rent: int | None = None
    discount_percent: float | None = None
