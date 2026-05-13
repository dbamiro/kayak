"""Typed API models shared by routers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    building_id: UUID
    name: str
    city: str
    dmv_area: str
    listing_id: UUID
    bedrooms: Decimal | None
    effective_rent_monthly: Decimal | None
    all_in_monthly: Decimal | None
    leasing_pressure_score: int | None
    negotiation_score: int | None
    snapshot_at: datetime


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
    leasing_pressure_score: int | None
    negotiation_score: int | None


class AlertCreate(BaseModel):
    email: str | None = None
    label: str | None = None
    criteria: dict[str, Any]


class AlertOut(BaseModel):
    id: UUID
    email: str | None
    label: str | None
    criteria: dict[str, Any]
    active: bool
    created_at: datetime
