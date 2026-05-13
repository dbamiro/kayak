"""Canonical listing shape produced by parsers before persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class CanonicalListing(BaseModel):
    """Normalized inventory row extracted from HTML/embedded JSON (site-agnostic)."""

    building_name: str | None = None
    address: str | None = None
    floorplan_name: str | None = None
    unit_label: str | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    listed_rent_min: int | None = None
    listed_rent_max: int | None = None
    available_date: str | None = None
    concession_text: str | None = None
    fee_text: str | None = None
    source_url: str
    scrape_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parser_name: str = "unknown"
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    field_confidence: dict[str, float] | None = Field(
        default=None,
        description="Per-field heuristics (0..1); optional diagnostic payload.",
    )
    raw_fragment: dict[str, Any] | str | None = None

    model_config = {"extra": "ignore"}
