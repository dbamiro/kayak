"""Recursive JSON discovery + normalization helpers for embedded apartment payloads."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from datetime import datetime, timezone

from models.canonical_listing import CanonicalListing

# Keys that suggest an apartment / pricing record (lowercase substrings match).
APARTMENT_KEY_HINTS = frozenset(
    {
        "rent",
        "price",
        "pricing",
        "monthlyrent",
        "baseRent",
        "floorplan",
        "floorplanname",
        "floorPlan",
        "unit",
        "unitnumber",
        "unitlabel",
        "beds",
        "bedrooms",
        "baths",
        "bathrooms",
        "sqft",
        "squarefeet",
        "square_feet",
        "availability",
        "availabledate",
        "moveindate",
        "specials",
        "concessions",
        "fees",
        "amenityfee",
    }
)


def _norm_key(k: Any) -> str:
    if isinstance(k, str):
        return re.sub(r"[^a-z0-9]", "", k.lower())
    return ""


def _flatten_keys(obj: dict[str, Any]) -> set[str]:
    return {_norm_key(k) for k in obj.keys()}


def _score_apartment_dict(obj: dict[str, Any]) -> int:
    keys = _flatten_keys(obj)
    score = 0
    for hint in APARTMENT_KEY_HINTS:
        hint_n = re.sub(r"[^a-z0-9]", "", hint.lower())
        if any(hint_n and hint_n in nk for nk in keys):
            score += 1
    # Strong signals
    if any(k in keys for k in ("rent", "price", "monthlyrent", "baserent")):
        score += 2
    if any("bed" in k for k in keys) or any(k in keys for k in ("beds", "bedrooms")):
        score += 1
    return score


def deep_find_candidate_objects(data: Any, *, min_score: int = 3) -> list[dict[str, Any]]:
    """Depth-first search for dicts that look like apartment pricing rows."""

    out: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            sc = _score_apartment_dict(node)
            if sc >= min_score:
                out.append(dict(node))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return out


def normalize_rent(value: Any) -> int | None:
    """Normalize rent / price scalars to whole USD (monthly assumption)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(round(value)) if value > 0 else None
    s = str(value).strip()
    if not s:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", s)
    if not cleaned:
        return None
    try:
        d = Decimal(cleaned)
    except InvalidOperation:
        return None
    if d <= 0:
        return None
    # Values like 2450.00 → int; "245000" cents unlikely in Next.js rent fields — keep as-is.
    return int(d.quantize(Decimal("1")))


def normalize_bedrooms(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    s = str(value).strip().lower()
    if s in {"studio", "eff", "efficiency"}:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_bathrooms(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    s = str(value).strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_sqft(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(round(value)) if value > 0 else None
    s = str(value).strip()
    m = re.search(r"([\d,]+)", s)
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    try:
        v = int(digits)
    except ValueError:
        return None
    return v if v > 0 else None


def extract_concession_text(obj: dict[str, Any]) -> str | None:
    """Pull human-readable concession/special strings from a heterogeneous dict."""
    keys_priority = (
        "specials",
        "concessions",
        "concession",
        "specialOffers",
        "special_offers",
        "leasingSpecials",
        "promotions",
    )
    for k in keys_priority:
        if k not in obj:
            continue
        val = obj[k]
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list):
            parts = [str(x).strip() for x in val if str(x).strip()]
            if parts:
                return "; ".join(parts[:12])
        if isinstance(val, dict):
            # shallow stringify
            parts = [f"{sk}: {sv}" for sk, sv in list(val.items())[:10]]
            if parts:
                return "; ".join(parts)
    return None


def extract_fee_text(obj: dict[str, Any]) -> str | None:
    keys_priority = (
        "fees",
        "feeDescription",
        "fee_details",
        "monthlyFees",
        "amenityFee",
        "amenity_fee",
        "parkingFee",
        "adminFee",
    )
    for k in keys_priority:
        if k not in obj:
            continue
        val = obj[k]
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, (list, dict)):
            try:
                return str(val)[:2000]
            except Exception:
                return None
    return None


def field_confidence_map(listing: CanonicalListing, obj: dict[str, Any]) -> dict[str, float]:
    """Lightweight per-field scores for debugging noisy extractions."""
    fc: dict[str, float] = {}
    if listing.listed_rent_min or listing.listed_rent_max:
        fc["rent"] = 0.9 if (_score_apartment_dict(obj) >= 4) else 0.65
    if listing.bedrooms is not None:
        fc["bedrooms"] = 0.85
    if listing.bathrooms is not None:
        fc["bathrooms"] = 0.85
    if listing.sqft:
        fc["sqft"] = 0.8
    if listing.floorplan_name:
        fc["floorplan"] = 0.75
    if listing.unit_label:
        fc["unit"] = 0.7
    if listing.available_date:
        fc["availability"] = 0.6
    if listing.concession_text:
        fc["concessions"] = 0.55
    if listing.fee_text:
        fc["fees"] = 0.55
    return fc


def confidence_score_for_listing(obj: dict[str, Any], listing: CanonicalListing) -> float:
    """Heuristic 0..1 confidence from field coverage + apartment dict strength."""
    score = 0.0
    max_pts = 10.0

    if listing.listed_rent_min or listing.listed_rent_max:
        score += 3.0
    if listing.bedrooms is not None:
        score += 1.5
    if listing.bathrooms is not None:
        score += 1.0
    if listing.sqft:
        score += 1.0
    if listing.floorplan_name or listing.unit_label:
        score += 1.5
    if listing.available_date:
        score += 0.5
    if listing.concession_text or listing.fee_text:
        score += 0.5

    dict_strength = min(2.0, _score_apartment_dict(obj) / 6.0)
    score += dict_strength

    return max(0.0, min(1.0, score / max_pts))


def candidate_to_canonical(
    obj: dict[str, Any],
    *,
    source_url: str,
    parser_name: str,
    scrape_ts: datetime | None,
    building_name_hint: str | None = None,
) -> CanonicalListing | None:
    """Map a heterogeneous dict to CanonicalListing using flexible key aliases."""

    def pick(*names: str) -> Any:
        for n in names:
            if n in obj:
                return obj[n]
        lowered = {_norm_key(k): k for k in obj.keys() if isinstance(k, str)}
        for n in names:
            nk = _norm_key(n)
            if nk in lowered:
                return obj[lowered[nk]]
        return None

    rent_min = pick(
        "listedRentMin",
        "rentMin",
        "minRent",
        "rent_from",
        "rentFrom",
        "priceMin",
        "startingRent",
        "rent",
        "price",
        "monthlyRent",
        "baseRent",
    )
    rent_max = pick("listedRentMax", "rentMax", "maxRent", "priceMax")

    rmin = normalize_rent(rent_min)
    rmax = normalize_rent(rent_max)

    # Single rent field often means min=max
    if rmin and not rmax:
        rmax = rmin
    if rmax and not rmin:
        rmin = rmax

    beds = normalize_bedrooms(pick("bedrooms", "beds", "bed", "bedRoomCount"))
    baths = normalize_bathrooms(pick("bathrooms", "baths", "bath", "bathroomsFull"))
    sqft = normalize_sqft(pick("sqft", "squareFeet", "square_feet", "squareFootage", "sqFt"))

    fp = pick("floorplan", "floorPlan", "floorplanName", "planName", "name", "title")
    unit = pick("unit", "unitNumber", "unit_label", "unitLabel", "aptNumber")

    avail = pick("availableDate", "availability", "availableOn", "moveInDate", "move_in_date")
    avail_s = str(avail) if avail not in (None, "") else None

    bname = pick("buildingName", "propertyName", "communityName", "community")
    addr = pick("address", "fullAddress", "street")

    conc = extract_concession_text(obj)
    fees = extract_fee_text(obj)

    scrape_ts = scrape_ts or datetime.now(timezone.utc)

    cl = CanonicalListing(
        building_name=(str(bname) if bname else building_name_hint),
        address=str(addr) if addr else None,
        floorplan_name=str(fp) if fp else None,
        unit_label=str(unit) if unit else None,
        bedrooms=beds,
        bathrooms=baths,
        sqft=sqft,
        listed_rent_min=rmin,
        listed_rent_max=rmax,
        available_date=avail_s,
        concession_text=conc,
        fee_text=fees,
        source_url=source_url,
        scrape_timestamp=scrape_ts,
        parser_name=parser_name,
        confidence_score=0.0,
        raw_fragment=obj,
    )
    cl.confidence_score = confidence_score_for_listing(obj, cl)
    cl.field_confidence = field_confidence_map(cl, obj)

    # Require some pricing signal to treat as listing
    if cl.listed_rent_min is None and cl.listed_rent_max is None:
        return None

    return cl
