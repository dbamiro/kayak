"""Parser interfaces: canonical `BaseParser` + legacy `ParsedListing` for older call sites."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from models.canonical_listing import CanonicalListing


@dataclass
class ParsedListing:
    """Legacy structured extraction result (used by older persistence helpers)."""

    external_key: str | None = None
    unit_label: str | None = None
    floorplan_name: str | None = None
    bedrooms: Decimal | None = None
    bathrooms: Decimal | None = None
    sqft: int | None = None
    base_rent_monthly: Decimal | None = None
    lease_term_months: int | None = None
    move_in_date: str | None = None
    availability_status: str | None = None
    concessions: dict[str, Any] = field(default_factory=dict)
    fees: dict[str, Any] = field(default_factory=dict)
    utilities_estimate: Decimal | None = None
    notes: str | None = None


class BaseParser(ABC):
    """Site/stack parser plugin operating on fetched HTML (and embedded JSON)."""

    source_type: str = "generic"
    name: str = "base"
    version: str = "0.0.1"

    @abstractmethod
    def can_parse(self, html: str, url: str) -> bool:
        """Return True when this parser understands the payload shape."""

    @abstractmethod
    def parse(self, html: str, url: str, metadata: dict[str, Any]) -> list[CanonicalListing]:
        """Produce zero or more canonical listings."""
