from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import Connection

from crawler.fetcher import FetchResult
from normalize.rents import compute_all_in_monthly, compute_effective_rent
from normalize.scores import leasing_pressure_score, negotiation_score
from parsers.base import ParsedListing


def _parse_move_in(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def insert_raw_capture(
    conn: Connection,
    *,
    building_id: UUID | None,
    listing_id: UUID | None,
    result: FetchResult,
) -> UUID:
    row = conn.execute(
        """
        INSERT INTO raw_captures (
            building_id, listing_id, source_url, fetch_mode, format, body, content_hash, http_status
        )
        VALUES (%(building_id)s, %(listing_id)s, %(source_url)s, %(fetch_mode)s, %(format)s,
                %(body)s, %(content_hash)s, %(http_status)s)
        RETURNING id
        """,
        {
            "building_id": str(building_id) if building_id else None,
            "listing_id": str(listing_id) if listing_id else None,
            "source_url": result.source_url,
            "fetch_mode": result.fetch_mode.value,
            "format": result.format,
            "body": result.body,
            "content_hash": result.content_hash,
            "http_status": result.http_status,
        },
    ).fetchone()
    conn.commit()
    return UUID(str(row[0]))


def insert_raw_document(
    conn: Connection,
    *,
    source_id: UUID | None,
    building_id: UUID | None,
    crawl_run_id: UUID | None,
    result: FetchResult,
) -> UUID:
    """Preferred audit trail for parser pipeline (`raw_documents`)."""
    row = conn.execute(
        """
        INSERT INTO raw_documents (
            source_id, building_id, crawl_run_id, source_url, fetch_mode, format,
            body, content_hash, http_status
        )
        VALUES (
            %(sid)s, %(bid)s, %(rid)s, %(url)s, %(fm)s, %(fmt)s,
            %(body)s, %(hash)s, %(st)s
        )
        RETURNING id
        """,
        {
            "sid": str(source_id) if source_id else None,
            "bid": str(building_id) if building_id else None,
            "rid": str(crawl_run_id) if crawl_run_id else None,
            "url": result.source_url,
            "fm": result.fetch_mode.value,
            "fmt": result.format,
            "body": result.body,
            "hash": result.content_hash,
            "st": result.http_status,
        },
    ).fetchone()
    conn.commit()
    return UUID(str(row[0]))


def prior_base_rent(conn: Connection, listing_id: UUID) -> Decimal | None:
    row = conn.execute(
        """
        SELECT base_rent_monthly
        FROM listing_snapshots
        WHERE listing_id = %s
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (str(listing_id),),
    ).fetchone()
    if row and row[0] is not None:
        return Decimal(str(row[0]))
    return None


def upsert_listing_and_snapshot(
    conn: Connection,
    *,
    building_id: UUID,
    parsed: ParsedListing,
    parser_name: str,
    parser_version: str,
) -> UUID:
    lease_months = parsed.lease_term_months or 12
    base_rent = parsed.base_rent_monthly or Decimal("0")
    if base_rent <= 0:
        raise ValueError("base_rent_monthly required for persistence")

    listing_row = conn.execute(
        """
        INSERT INTO listings (building_id, external_key, unit_label, floorplan_name, bedrooms, bathrooms, sqft)
        VALUES (%(b)s, %(ek)s, %(ul)s, %(fn)s, %(br)s, %(ba)s, %(sq)s)
        ON CONFLICT (building_id, external_key)
        DO UPDATE SET
            unit_label = COALESCE(EXCLUDED.unit_label, listings.unit_label),
            floorplan_name = COALESCE(EXCLUDED.floorplan_name, listings.floorplan_name),
            bedrooms = COALESCE(EXCLUDED.bedrooms, listings.bedrooms),
            bathrooms = COALESCE(EXCLUDED.bathrooms, listings.bathrooms),
            sqft = COALESCE(EXCLUDED.sqft, listings.sqft)
        RETURNING id
        """,
        {
            "b": str(building_id),
            "ek": parsed.external_key,
            "ul": parsed.unit_label,
            "fn": parsed.floorplan_name,
            "br": parsed.bedrooms,
            "ba": parsed.bathrooms,
            "sq": parsed.sqft,
        },
    ).fetchone()
    listing_id = UUID(str(listing_row[0]))

    prev_base = prior_base_rent(conn, listing_id)
    eff = compute_effective_rent(base_rent, lease_months, parsed.concessions)
    all_in = compute_all_in_monthly(eff, parsed.fees, parsed.utilities_estimate)

    lp = leasing_pressure_score(
        base_rent_monthly=base_rent,
        concessions=parsed.concessions,
        fees=parsed.fees,
        availability_status=parsed.availability_status,
        prior_base_rent_monthly=prev_base,
    )
    neg = negotiation_score(lp, base_rent, parsed.concessions, parsed.fees)

    conn.execute(
        """
        INSERT INTO listing_snapshots (
            listing_id, base_rent_monthly, lease_term_months, move_in_date, availability_status,
            concessions, fees, utilities_estimate, effective_rent_monthly, all_in_monthly,
            leasing_pressure_score, negotiation_score, parser_name, parser_version, notes
        )
        VALUES (
            %(lid)s, %(br)s, %(lm)s, %(mid)s, %(av)s,
            %(con)s::jsonb, %(fe)s::jsonb, %(ue)s, %(ef)s, %(ai)s,
            %(lp)s, %(ng)s, %(pn)s, %(pv)s, %(no)s
        )
        """,
        {
            "lid": str(listing_id),
            "br": base_rent,
            "lm": lease_months,
            "mid": _parse_move_in(parsed.move_in_date),
            "av": parsed.availability_status,
            "con": json.dumps(parsed.concessions or {}),
            "fe": json.dumps(parsed.fees or {}),
            "ue": parsed.utilities_estimate,
            "ef": eff,
            "ai": all_in,
            "lp": lp,
            "ng": neg,
            "pn": parser_name,
            "pv": parser_version,
            "no": parsed.notes,
        },
    )
    conn.commit()
    return listing_id


def open_crawl_run(conn: Connection) -> UUID:
    row = conn.execute(
        "INSERT INTO crawl_runs (status) VALUES ('running') RETURNING id",
    ).fetchone()
    conn.commit()
    return UUID(str(row[0]))


def finish_crawl_run(conn: Connection, run_id: UUID, stats: dict[str, Any], error: str | None = None) -> None:
    conn.execute(
        """
        UPDATE crawl_runs
        SET finished_at = now(), status = %(st)s, stats = %(stats)s::jsonb, error_message = %(err)s
        WHERE id = %(id)s
        """,
        {
            "st": "failed" if error else "ok",
            "stats": json.dumps(stats),
            "err": error,
            "id": str(run_id),
        },
    )
    conn.commit()
