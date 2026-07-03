"""Persist `CanonicalListing` rows into floorplans, units, listings, snapshots, and aux tables."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import Connection

from models.canonical_listing import CanonicalListing
from normalize.rents import compute_all_in_monthly, compute_effective_rent
from normalize.scores import leasing_pressure_score, negotiation_score
from app.services.crawl_incentive_service import concession_dict_from_text, persist_crawled_incentive
from crawler.persist import prior_base_rent

logger = logging.getLogger(__name__)


def _slug(s: str | None, fallback: str) -> str:
    x = (s or fallback).lower()
    x = re.sub(r"[^a-z0-9]+", "-", x).strip("-")
    return (x or fallback)[:48]


def _listing_external_key(cl: CanonicalListing) -> str:
    fp = _slug(cl.floorplan_name, "fp")
    u = _slug(cl.unit_label, "unit")
    bed = str(cl.bedrooms) if cl.bedrooms is not None else "x"
    raw = f"{fp}|{u}|{bed}|{cl.source_url}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    key = f"{fp}-{u}-{bed}-{digest}"
    return key[:200]


def _parse_move_in(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _base_rent(cl: CanonicalListing) -> Decimal:
    if cl.listed_rent_min is not None and cl.listed_rent_max is not None:
        return Decimal(str(int(round((cl.listed_rent_min + cl.listed_rent_max) / 2))))
    if cl.listed_rent_min is not None:
        return Decimal(str(cl.listed_rent_min))
    if cl.listed_rent_max is not None:
        return Decimal(str(cl.listed_rent_max))
    return Decimal("0")


def upsert_floorplan(
    conn: Connection,
    *,
    building_id: UUID,
    canonical: CanonicalListing,
) -> UUID | None:
    if not canonical.floorplan_name and canonical.bedrooms is None:
        return None
    ek = _slug(canonical.floorplan_name, "plan") + "-" + str(canonical.bedrooms if canonical.bedrooms is not None else "na")
    row = conn.execute(
        """
        INSERT INTO floorplans (building_id, external_key, name, bedrooms, bathrooms, sqft, metadata)
        VALUES (%(b)s, %(ek)s, %(nm)s, %(br)s, %(ba)s, %(sq)s, %(md)s::jsonb)
        ON CONFLICT (building_id, external_key)
        DO UPDATE SET
            name = COALESCE(EXCLUDED.name, floorplans.name),
            bedrooms = COALESCE(EXCLUDED.bedrooms, floorplans.bedrooms),
            bathrooms = COALESCE(EXCLUDED.bathrooms, floorplans.bathrooms),
            sqft = COALESCE(EXCLUDED.sqft, floorplans.sqft)
        RETURNING id
        """,
        {
            "b": str(building_id),
            "ek": ek[:200],
            "nm": canonical.floorplan_name,
            "br": Decimal(str(canonical.bedrooms)) if canonical.bedrooms is not None else None,
            "ba": Decimal(str(canonical.bathrooms)) if canonical.bathrooms is not None else None,
            "sq": canonical.sqft,
            "md": json.dumps({"source": "canonical_listing"}),
        },
    ).fetchone()
    return UUID(str(row[0])) if row else None


def upsert_unit_row(
    conn: Connection,
    *,
    building_id: UUID,
    floorplan_id: UUID | None,
    canonical: CanonicalListing,
) -> UUID | None:
    label = canonical.unit_label or "_building_level"
    ek = _slug(label, "u") + "-" + (str(floorplan_id)[:8] if floorplan_id else "nofp")
    row = conn.execute(
        """
        INSERT INTO units (building_id, floorplan_id, external_key, unit_label, metadata)
        VALUES (%(b)s, %(fp)s, %(ek)s, %(ul)s, %(md)s::jsonb)
        ON CONFLICT (building_id, external_key)
        DO UPDATE SET
            floorplan_id = COALESCE(EXCLUDED.floorplan_id, units.floorplan_id),
            unit_label = COALESCE(EXCLUDED.unit_label, units.unit_label)
        RETURNING id
        """,
        {
            "b": str(building_id),
            "fp": str(floorplan_id) if floorplan_id else None,
            "ek": ek[:200],
            "ul": canonical.unit_label,
            "md": json.dumps({}),
        },
    ).fetchone()
    return UUID(str(row[0])) if row else None


def persist_canonical_listing(
    conn: Connection,
    *,
    building_id: UUID,
    raw_document_id: UUID | None,
    canonical: CanonicalListing,
    parser_version: str | None = None,
) -> UUID:
    """Append-only snapshot row; never updates historical snapshots."""
    pn = canonical.parser_name
    pv = parser_version or ""
    if "@" in pn:
        pn_only, pv_auto = pn.split("@", 1)
        pn = pn_only
        pv = pv or pv_auto

    base = _base_rent(canonical)
    if base <= 0:
        raise ValueError("canonical listing missing rent")

    floorplan_id = upsert_floorplan(conn, building_id=building_id, canonical=canonical)
    unit_id = upsert_unit_row(conn, building_id=building_id, floorplan_id=floorplan_id, canonical=canonical)

    ek = _listing_external_key(canonical)
    listing_row = conn.execute(
        """
        INSERT INTO listings (
            building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft,
            floorplan_id, unit_id
        )
        VALUES (
            %(b)s, %(ek)s, %(ul)s, %(fn)s, %(br)s, %(ba)s, %(sq)s, %(fp)s, %(uid)s
        )
        ON CONFLICT (building_id, external_key)
        DO UPDATE SET
            unit_label = COALESCE(EXCLUDED.unit_label, listings.unit_label),
            floorplan_name = COALESCE(EXCLUDED.floorplan_name, listings.floorplan_name),
            bedrooms = COALESCE(EXCLUDED.bedrooms, listings.bedrooms),
            bathrooms = COALESCE(EXCLUDED.bathrooms, listings.bathrooms),
            sqft = COALESCE(EXCLUDED.sqft, listings.sqft),
            floorplan_id = COALESCE(EXCLUDED.floorplan_id, listings.floorplan_id),
            unit_id = COALESCE(EXCLUDED.unit_id, listings.unit_id)
        RETURNING id
        """,
        {
            "b": str(building_id),
            "ek": ek,
            "ul": canonical.unit_label,
            "fn": canonical.floorplan_name,
            "br": Decimal(str(canonical.bedrooms)) if canonical.bedrooms is not None else None,
            "ba": Decimal(str(canonical.bathrooms)) if canonical.bathrooms is not None else None,
            "sq": canonical.sqft,
            "fp": str(floorplan_id) if floorplan_id else None,
            "uid": str(unit_id) if unit_id else None,
        },
    ).fetchone()
    listing_id = UUID(str(listing_row[0]))

    prev_base = prior_base_rent(conn, listing_id)
    lease_months = 12
    structured_conc: dict[str, Any] = {}
    if canonical.concession_text:
        structured_conc = concession_dict_from_text(canonical.concession_text)
    structured_fees: dict[str, Any] = {}
    if canonical.fee_text:
        structured_fees = {"raw_text": canonical.fee_text}

    eff = compute_effective_rent(base, lease_months, structured_conc if structured_conc else {})
    all_in = compute_all_in_monthly(eff, structured_fees if structured_fees else {}, None)

    lp = leasing_pressure_score(
        base_rent_monthly=base,
        concessions=structured_conc if structured_conc else {},
        fees=structured_fees if structured_fees else {},
        availability_status=canonical.available_date,
        prior_base_rent_monthly=prev_base,
    )
    neg = negotiation_score(lp, base, structured_conc if structured_conc else {}, structured_fees if structured_fees else {})

    raw_frag_json = canonical.raw_fragment
    if isinstance(raw_frag_json, dict):
        frag_payload = raw_frag_json
    else:
        frag_payload = {"value": raw_frag_json}

    snap = conn.execute(
        """
        INSERT INTO listing_snapshots (
            listing_id, base_rent_monthly, lease_term_months, move_in_date, availability_status,
            concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
            leasing_pressure_score, negotiation_score, parser_name, parser_version, notes,
            raw_document_id, parser_confidence, raw_fragment, field_confidences
        )
        VALUES (
            %(lid)s, %(br)s, %(lm)s, %(mid)s, %(av)s,
            %(con)s::jsonb, %(fe)s::jsonb, %(ue)s, %(ef)s, %(ai)s,
            %(lp)s, %(ng)s, %(pn)s, %(pv)s, %(no)s,
            %(rd)s, %(pc)s, %(rf)s::jsonb, %(fcf)s::jsonb
        )
        RETURNING id
        """,
        {
            "lid": str(listing_id),
            "br": base,
            "lm": lease_months,
            "mid": _parse_move_in(canonical.available_date),
            "av": canonical.available_date,
            "con": json.dumps(structured_conc),
            "fe": json.dumps(structured_fees),
            "ue": None,
            "ef": eff,
            "ai": all_in,
            "lp": lp,
            "ng": neg,
            "pn": pn,
            "pv": pv,
            "no": canonical.concession_text or canonical.fee_text,
            "rd": str(raw_document_id) if raw_document_id else None,
            "pc": canonical.confidence_score,
            "rf": json.dumps(frag_payload) if frag_payload is not None else json.dumps({}),
            "fcf": json.dumps(canonical.field_confidence or {}),
        },
    ).fetchone()
    snapshot_id = UUID(str(snap[0]))

    if canonical.concession_text:
        conn.execute(
            """
            INSERT INTO snapshot_concessions (listing_snapshot_id, raw_text, parser_confidence)
            VALUES (%s, %s, %s)
            """,
            (str(snapshot_id), canonical.concession_text, canonical.confidence_score),
        )
    if canonical.fee_text:
        conn.execute(
            """
            INSERT INTO snapshot_fees (listing_snapshot_id, raw_text, parser_confidence)
            VALUES (%s, %s, %s)
            """,
            (str(snapshot_id), canonical.fee_text, canonical.confidence_score),
        )

    persist_crawled_incentive(
        conn,
        building_id=building_id,
        listing_id=listing_id,
        listing_snapshot_id=snapshot_id,
        concession_text=canonical.concession_text,
        fee_text=canonical.fee_text,
        listed_rent=int(base),
        lease_term_months=lease_months,
        source_url=canonical.source_url,
        parser_name=pn,
        parser_confidence=canonical.confidence_score,
    )

    conn.commit()
    return listing_id
