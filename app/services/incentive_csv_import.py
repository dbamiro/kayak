"""Admin CSV bulk import for verified real incentives."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.services.incentive_calculator import weeks_free_to_months
from app.services.incentive_service import create_incentive, merge_parsed_into_data, resolve_building_id
from app.services.incentive_text_parser import parse_incentive_text

# Canonical CSV columns (aliases normalized to these keys).
CANONICAL_HEADERS = {
    "building_name",
    "address_or_area",
    "city",
    "state",
    "neighborhood",
    "unit_or_floorplan",
    "listed_rent",
    "lease_term_months",
    "free_months",
    "free_weeks",
    "rent_credit",
    "waived_fees",
    "source_url",
    "expiration_date",
    "notes",
}

HEADER_ALIASES: dict[str, set[str]] = {
    "building_name": {"building_name", "building", "property_name", "name"},
    "address_or_area": {
        "address_or_area",
        "address",
        "address_area",
        "address/area",
        "street_address",
        "area",
    },
    "city": {"city"},
    "state": {"state"},
    "neighborhood": {
        "neighborhood",
        "market",
        "neighborhood_or_market",
        "neighborhood_market",
        "dmv_market",
        "area_market",
    },
    "unit_or_floorplan": {"unit_or_floorplan", "unit", "floorplan", "unit_floorplan", "unit/floorplan"},
    "listed_rent": {"listed_rent", "rent", "listed rent"},
    "lease_term_months": {
        "lease_term_months",
        "lease_months",
        "lease_term",
        "lease term",
        "term_months",
    },
    "free_months": {"free_months", "free months", "months_free"},
    "free_weeks": {"free_weeks", "free weeks", "weeks_free"},
    "rent_credit": {"rent_credit", "rent credit", "credit", "custom_credit"},
    "waived_fees": {"waived_fees", "waived fees", "waived_fee", "fee_waiver"},
    "source_url": {"source_url", "source url", "url", "verification_url"},
    "expiration_date": {
        "expiration_date",
        "expires_at",
        "expires",
        "expiration date",
        "expiry",
        "expiry_date",
    },
    "notes": {"notes", "note", "raw_text", "special_text"},
}

EXAMPLE_MARKERS = (
    "example only",
    "[example",
    "sample only",
    "do not import",
    "fake building",
)

EXAMPLE_URL_HOSTS = ("example.com", "example.org", "example.net")


@dataclass
class CsvRowError:
    row: int
    field: str | None
    message: str


@dataclass
class CsvImportResult:
    dry_run: bool = False
    created_count: int = 0
    error_count: int = 0
    errors: list[CsvRowError] = field(default_factory=list)
    created_incentive_ids: list[UUID] = field(default_factory=list)


def _normalize_header(raw: str) -> str | None:
    key = re.sub(r"[\s/]+", "_", raw.strip().lower())
    key = re.sub(r"[^a-z0-9_]", "", key)
    for canonical, aliases in HEADER_ALIASES.items():
        if key in aliases or key == canonical:
            return canonical
    return None


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "building")[:48]


def _parse_int(value: str | None, *, field: str, row: int, errors: list[CsvRowError], required: bool = False) -> int | None:
    if value is None or not str(value).strip():
        if required:
            errors.append(CsvRowError(row, field, f"{field} is required"))
        return None
    raw = str(value).strip().replace(",", "").replace("$", "")
    try:
        n = int(float(raw))
    except ValueError:
        errors.append(CsvRowError(row, field, f"{field} must be a number (got {value!r})"))
        return None
    if n <= 0 and field in ("listed_rent", "lease_term_months"):
        errors.append(CsvRowError(row, field, f"{field} must be greater than zero"))
        return None
    return n


def _parse_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).strip().replace(",", ""))
    except ValueError:
        return None


def _parse_date(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_address_area(raw: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    """Return address_line1, city, state, neighborhood hint."""
    if not raw or not raw.strip():
        return None, None, None, None
    text = raw.strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[0], parts[-2], parts[-1].split()[0][:2].upper(), None
    if len(parts) == 2:
        return None, parts[0], parts[1].split()[0][:2].upper(), None
    return None, parts[0], None, parts[0]


def infer_dmv_area(city: str | None, state: str | None, area_hint: str | None = None) -> str | None:
    blob = " ".join(filter(None, [city, state, area_hint])).lower()
    mapping = [
        (("washington", " dc", "district of columbia"), "DC"),
        (("arlington",), "ARLINGTON"),
        (("alexandria",), "ALEXANDRIA"),
        (("tyson",), "TYSONS"),
        (("reston",), "RESTON"),
        (("ashburn",), "ASHBURN"),
        (("silver spring",), "SILVER_SPRING"),
        (("bethesda",), "BETHESDA"),
    ]
    for needles, area in mapping:
        if any(n in blob for n in needles):
            return area
    if state and state.upper() == "DC":
        return "DC"
    return None


def _is_example_row(row: dict[str, str]) -> bool:
    name = (row.get("building_name") or "").lower()
    url = (row.get("source_url") or "").lower()
    notes = (row.get("notes") or "").lower()
    if any(m in name for m in EXAMPLE_MARKERS):
        return True
    if any(m in notes for m in EXAMPLE_MARKERS):
        return True
    if any(host in url for host in EXAMPLE_URL_HOSTS):
        return True
    return False


def _validate_url(value: str | None, row: int, errors: list[CsvRowError]) -> str | None:
    if not value or not value.strip():
        errors.append(CsvRowError(row, "source_url", "source_url is required for admin-verified imports"))
        return None
    url = value.strip()
    if not re.match(r"^https?://", url, re.I):
        errors.append(CsvRowError(row, "source_url", "source_url must start with http:// or https://"))
        return None
    return url


def _build_raw_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("free_months"):
        parts.append(f"{row['free_months']} months free")
    if row.get("free_weeks"):
        parts.append(f"{row['free_weeks']} weeks free")
    if row.get("rent_credit"):
        parts.append(f"${row['rent_credit']} rent credit")
    if row.get("waived_fees"):
        parts.append(f"${row['waived_fees']} waived fees")
    if row.get("unit_or_floorplan"):
        parts.append(f"Applies to {row['unit_or_floorplan']}")
    if row.get("notes"):
        parts.append(str(row["notes"]))
    return ". ".join(parts) if parts else str(row.get("notes") or "Admin-verified move-in special")


def _infer_incentive_type(row: dict[str, Any]) -> str:
    if row.get("free_weeks"):
        return "free_weeks"
    if row.get("free_months"):
        return "free_months"
    if row.get("waived_fees"):
        return "fee_waiver"
    if row.get("rent_credit"):
        return "rent_credit"
    return "unknown"


def _unique_building_slug(conn: Connection, base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    n = 0
    while True:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM buildings WHERE slug = %s LIMIT 1", (candidate,))
            if not cur.fetchone():
                return candidate
        n += 1
        candidate = f"{slug}-{n}"[:56]


def ensure_building_for_import(
    conn: Connection,
    *,
    building_name: str,
    address_or_area: str | None,
    city: str | None,
    state: str | None,
    source_url: str,
    neighborhood: str | None = None,
) -> UUID:
    """Match existing building or create one from admin CSV row (real address + source URL)."""
    bid = resolve_building_id(conn, building_name=building_name, city=city)
    if bid:
        return bid

    addr, parsed_city, parsed_state, hint = _parse_address_area(address_or_area)
    city = city or parsed_city
    state = (state or parsed_state or "VA").upper()[:2]
    if not city:
        raise ValueError("city or parseable address_or_area is required when building does not exist")

    dmv_area = infer_dmv_area(city, state, address_or_area)
    if not dmv_area:
        raise ValueError(
            f"Could not infer dmv_area for city={city!r} — use a DMV city or add city/state columns"
        )

    slug = _unique_building_slug(conn, f"{building_name}-{city}")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO buildings (
                name, slug, address_line1, city, state, neighborhood, dmv_area, property_url, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::dmv_area, %s, %s::jsonb)
            RETURNING id
            """,
            (
                building_name.strip(),
                slug,
                addr,
                city,
                state,
                neighborhood or hint,
                dmv_area,
                source_url,
                Json({"import_source": "admin_csv", "verified_by_admin": True}),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return UUID(str(row["id"]))


def ensure_listing_for_import(
    conn: Connection,
    *,
    building_id: UUID,
    listed_rent: int,
    lease_term_months: int,
    unit_or_floorplan: str | None = None,
) -> None:
    """Minimal listing so CSV-imported buildings appear in /search (admin-provided rent)."""
    external_key = f"csv-import-{building_id}"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id FROM listings WHERE building_id = %s AND external_key = %s LIMIT 1",
            (str(building_id), external_key),
        )
        if cur.fetchone():
            return
        cur.execute(
            """
            INSERT INTO listings (building_id, external_key, unit_label, floorplan_name)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (str(building_id), external_key, unit_or_floorplan, unit_or_floorplan),
        )
        listing_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO listing_snapshots (listing_id, base_rent_monthly, lease_term_months, availability_status)
            VALUES (%s, %s, %s, 'available')
            """,
            (str(listing_id), listed_rent, lease_term_months),
        )
    conn.commit()


def parse_csv_rows(content: str | bytes) -> tuple[list[dict[str, str]], list[CsvRowError]]:
    """Parse CSV and normalize headers. Returns data rows (1-based line numbers in errors)."""
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return [], [CsvRowError(1, None, "CSV is empty or missing header row")]

    col_map: dict[str, str] = {}
    errors: list[CsvRowError] = []
    for raw in reader.fieldnames:
        canon = _normalize_header(raw or "")
        if canon:
            col_map[raw] = canon
        elif raw and raw.strip():
            errors.append(CsvRowError(1, raw, f"Unrecognized column {raw!r}"))

    if "building_name" not in col_map.values():
        errors.append(CsvRowError(1, None, "Missing required column building_name"))
    if "listed_rent" not in col_map.values():
        errors.append(CsvRowError(1, None, "Missing required column listed_rent"))
    if "lease_term_months" not in col_map.values():
        errors.append(CsvRowError(1, None, "Missing required column lease_term_months"))
    if "source_url" not in col_map.values():
        errors.append(CsvRowError(1, None, "Missing required column source_url"))
    if errors:
        return [], errors

    rows: list[dict[str, str]] = []
    for line_no, raw_row in enumerate(reader, start=2):
        if not any(v and str(v).strip() for v in raw_row.values()):
            continue
        normalized: dict[str, str] = {}
        for raw_key, val in raw_row.items():
            canon = col_map.get(raw_key or "")
            if canon and val is not None:
                normalized[canon] = str(val).strip()
        rows.append({"_line": str(line_no), **normalized})
    return rows, []


def validate_and_import_csv(
    conn: Connection,
    content: str | bytes,
    *,
    admin_user_id: UUID,
    dry_run: bool = False,
) -> CsvImportResult:
    result = CsvImportResult(dry_run=dry_run)
    rows, parse_errors = parse_csv_rows(content)
    result.errors.extend(parse_errors)
    if parse_errors:
        result.error_count = len(parse_errors)
        return result

    validated: list[tuple[int, dict[str, Any]]] = []

    for raw in rows:
        line = int(raw.pop("_line", 0))
        row_errors: list[CsvRowError] = []

        if _is_example_row(raw):
            row_errors.append(
                CsvRowError(
                    line,
                    "building_name",
                    "Row looks like example/sample data — remove EXAMPLE markers before importing",
                )
            )

        building_name = (raw.get("building_name") or "").strip()
        if not building_name:
            row_errors.append(CsvRowError(line, "building_name", "building_name is required"))

        listed_rent = _parse_int(raw.get("listed_rent"), field="listed_rent", row=line, errors=row_errors, required=True)
        lease_term = _parse_int(
            raw.get("lease_term_months"), field="lease_term_months", row=line, errors=row_errors, required=True
        )
        if lease_term is not None and lease_term > 60:
            row_errors.append(CsvRowError(line, "lease_term_months", "lease_term_months must be 60 or less"))

        source_url = _validate_url(raw.get("source_url"), line, row_errors)

        free_months = _parse_float(raw.get("free_months"))
        free_weeks = _parse_float(raw.get("free_weeks"))
        rent_credit = _parse_int(raw.get("rent_credit"), field="rent_credit", row=line, errors=row_errors)
        waived_fees = _parse_int(raw.get("waived_fees"), field="waived_fees", row=line, errors=row_errors)

        if free_months is not None and free_months < 0:
            row_errors.append(CsvRowError(line, "free_months", "free_months cannot be negative"))
        if free_weeks is not None and free_weeks < 0:
            row_errors.append(CsvRowError(line, "free_weeks", "free_weeks cannot be negative"))

        has_concession = any(
            v is not None and v != 0
            for v in (free_months, free_weeks, rent_credit, waived_fees)
        ) or bool(raw.get("notes"))
        if not has_concession:
            row_errors.append(
                CsvRowError(
                    line,
                    None,
                    "Provide at least one concession: free_months, free_weeks, rent_credit, waived_fees, or notes",
                )
            )

        addr, parsed_city, parsed_state, _ = _parse_address_area(raw.get("address_or_area"))
        city = raw.get("city") or parsed_city
        state = raw.get("state") or parsed_state
        neighborhood = (raw.get("neighborhood") or "").strip() or None

        expires_at = _parse_date(raw.get("expiration_date"))
        if raw.get("expiration_date") and expires_at is None:
            row_errors.append(
                CsvRowError(line, "expires_at", "expires_at must be YYYY-MM-DD or MM/DD/YYYY")
            )

        if row_errors:
            result.errors.extend(row_errors)
            continue

        effective_free_months = free_months
        if free_weeks and not free_months:
            effective_free_months = weeks_free_to_months(free_weeks)

        payload: dict[str, Any] = {
            "building_name": building_name,
            "address_or_area": raw.get("address_or_area"),
            "city": city,
            "state": state,
            "neighborhood": neighborhood,
            "address_line1": addr,
            "unit_or_floorplan": raw.get("unit_or_floorplan"),
            "listed_rent": listed_rent,
            "lease_term_months": lease_term,
            "free_months": effective_free_months,
            "free_weeks": free_weeks,
            "rent_credit": rent_credit,
            "waived_fees": waived_fees,
            "source_url": source_url,
            "expires_at": expires_at,
            "notes": raw.get("notes"),
        }
        validated.append((line, payload))

    result.error_count = len(result.errors)
    if dry_run:
        result.created_count = len(validated)
        return result

    if not validated:
        return result

    now = datetime.now(timezone.utc)
    for _line, payload in validated:
        try:
            building_id = ensure_building_for_import(
                conn,
                building_name=payload["building_name"],
                address_or_area=payload.get("address_or_area"),
                city=payload.get("city"),
                state=payload.get("state"),
                source_url=payload["source_url"],
                neighborhood=payload.get("neighborhood"),
            )
        except ValueError as exc:
            result.errors.append(CsvRowError(_line, "building_name", str(exc)))
            result.error_count += 1
            continue

        raw_text = _build_raw_text(payload)
        parsed = parse_incentive_text(raw_text)
        meta: dict[str, Any] = {"import_source": "admin_csv"}
        if payload.get("free_weeks"):
            meta["weeks_free"] = payload["free_weeks"]
        if payload.get("notes"):
            meta["import_notes"] = payload["notes"]
        if payload.get("neighborhood"):
            meta["neighborhood"] = payload["neighborhood"]
        if payload.get("unit_or_floorplan"):
            meta["unit_or_floorplan"] = payload["unit_or_floorplan"]

        data = merge_parsed_into_data(
            {
                "building_id": building_id,
                "source_url": payload["source_url"],
                "listed_rent": payload["listed_rent"],
                "lease_term_months": payload["lease_term_months"],
                "free_months": payload.get("free_months"),
                "waived_fee_amount": payload.get("waived_fees") or 0,
                "custom_credit_amount": payload.get("rent_credit") or 0,
                "raw_text": raw_text,
                "applies_to": payload.get("unit_or_floorplan"),
                "expires_at": payload.get("expires_at"),
                "verification_method": "admin_csv_verified",
                "capture_method": "admin_csv_import",
                "confidence_score": max(parsed.confidence_score, 0.9),
                "is_demo": False,
                "status": "verified",
                "verified_at": now,
                "reviewed_at": now,
                "reviewed_by_user_id": admin_user_id,
                "incentive_type": _infer_incentive_type(payload),
                "metadata": meta,
            },
            parsed,
        )
        if data.get("incentive_type") == "unknown" and parsed.incentive_type != "unknown":
            data["incentive_type"] = parsed.incentive_type
        if not data.get("incentive_type") or data["incentive_type"] == "unknown":
            data["incentive_type"] = "custom"

        row = create_incentive(conn, data)
        ensure_listing_for_import(
            conn,
            building_id=building_id,
            listed_rent=payload["listed_rent"],
            lease_term_months=payload["lease_term_months"],
            unit_or_floorplan=payload.get("unit_or_floorplan"),
        )
        result.created_incentive_ids.append(UUID(str(row["id"])))
        result.created_count += 1

    result.error_count = len(result.errors)
    return result
