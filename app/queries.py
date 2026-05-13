"""SQL helpers — keep routers thin."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json


def search_buildings(
    conn: Connection,
    *,
    city: str | None,
    dmv_area: str | None,
    min_rent: Decimal | None,
    max_rent: Decimal | None,
    bedrooms_min: Decimal | None,
) -> list[dict[str, Any]]:
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (listing_id)
                listing_id,
                captured_at,
                effective_rent_monthly,
                all_in_monthly,
                leasing_pressure_score,
                negotiation_score
            FROM listing_snapshots
            ORDER BY listing_id, captured_at DESC
        )
        SELECT
            b.id AS building_id,
            b.name,
            b.city,
            b.dmv_area::text AS dmv_area,
            l.id AS listing_id,
            l.bedrooms,
            ls.effective_rent_monthly,
            ls.all_in_monthly,
            ls.leasing_pressure_score,
            ls.negotiation_score,
            ls.captured_at AS snapshot_at
        FROM buildings b
        JOIN listings l ON l.building_id = b.id
        JOIN latest ls ON ls.listing_id = l.id
        WHERE (%(apply_city)s = false OR b.city ILIKE %(city_like)s)
          AND (%(apply_area)s = false OR b.dmv_area = %(dmv_area)s::dmv_area)
          AND (%(apply_min_rent)s = false OR ls.effective_rent_monthly >= %(min_rent)s)
          AND (%(apply_max_rent)s = false OR ls.effective_rent_monthly <= %(max_rent)s)
          AND (%(apply_bedrooms)s = false OR l.bedrooms >= %(bedrooms_min)s)
        ORDER BY b.name, l.bedrooms NULLS LAST
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            sql,
            {
                "apply_city": city is not None,
                "city_like": f"%{city}%" if city else "",
                "apply_area": dmv_area is not None,
                "dmv_area": dmv_area,
                "apply_min_rent": min_rent is not None,
                "min_rent": min_rent,
                "apply_max_rent": max_rent is not None,
                "max_rent": max_rent,
                "apply_bedrooms": bedrooms_min is not None,
                "bedrooms_min": bedrooms_min,
            },
        )
        return list(cur.fetchall())


def get_building(conn: Connection, building_id: UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, name, slug, city, state, postal_code, neighborhood, dmv_area::text AS dmv_area,
                   property_url, latitude, longitude
            FROM buildings
            WHERE id = %s
            """,
            (str(building_id),),
        )
        return cur.fetchone()


def list_building_quotes(conn: Connection, building_id: UUID) -> list[dict[str, Any]]:
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (listing_id)
                listing_id,
                captured_at,
                base_rent_monthly,
                effective_rent_monthly,
                all_in_monthly,
                leasing_pressure_score,
                negotiation_score,
                concessions,
                fees
            FROM listing_snapshots
            ORDER BY listing_id, captured_at DESC
        )
        SELECT
            l.id AS listing_id,
            l.unit_label,
            l.floorplan_name,
            l.bedrooms,
            l.bathrooms,
            l.sqft,
            ls.captured_at AS snapshot_at,
            ls.base_rent_monthly,
            ls.effective_rent_monthly,
            ls.all_in_monthly,
            ls.leasing_pressure_score,
            ls.negotiation_score,
            ls.concessions,
            ls.fees
        FROM listings l
        JOIN latest ls ON ls.listing_id = l.id
        WHERE l.building_id = %s
        ORDER BY l.bedrooms NULLS LAST, l.floorplan_name NULLS LAST
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (str(building_id),))
        return list(cur.fetchall())


def listing_history(conn: Connection, building_id: UUID) -> list[dict[str, Any]]:
    sql = """
        SELECT
            l.id AS listing_id,
            l.floorplan_name,
            ls.captured_at,
            ls.base_rent_monthly,
            ls.effective_rent_monthly,
            ls.all_in_monthly,
            ls.leasing_pressure_score,
            ls.negotiation_score
        FROM listing_snapshots ls
        JOIN listings l ON l.id = ls.listing_id
        WHERE l.building_id = %s
        ORDER BY ls.captured_at ASC
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (str(building_id),))
        return list(cur.fetchall())


def compare_buildings(
    conn: Connection,
    *,
    building_ids: list[UUID],
    bedrooms_min: Decimal | None,
) -> list[dict[str, Any]]:
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (listing_id)
                listing_id,
                captured_at,
                effective_rent_monthly,
                all_in_monthly,
                leasing_pressure_score,
                negotiation_score
            FROM listing_snapshots
            ORDER BY listing_id, captured_at DESC
        )
        SELECT
            b.id AS building_id,
            b.name AS building_name,
            b.city,
            b.dmv_area::text AS dmv_area,
            l.id AS listing_id,
            l.bedrooms,
            ls.effective_rent_monthly,
            ls.all_in_monthly,
            ls.leasing_pressure_score,
            ls.negotiation_score
        FROM buildings b
        JOIN listings l ON l.building_id = b.id
        JOIN latest ls ON ls.listing_id = l.id
        WHERE b.id = ANY(%(ids)s::uuid[])
          AND (%(apply_bedrooms)s = false OR l.bedrooms >= %(bedrooms_min)s)
        ORDER BY b.name, l.bedrooms NULLS LAST
    """
    ids = [str(i) for i in building_ids]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            sql,
            {"ids": ids, "apply_bedrooms": bedrooms_min is not None, "bedrooms_min": bedrooms_min},
        )
        return list(cur.fetchall())


def insert_alert(conn: Connection, payload: dict[str, Any]) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO alerts (email, label, criteria)
            VALUES (%(email)s, %(label)s, %(criteria)s)
            RETURNING id, email, label, criteria, active, created_at
            """,
            {
                "email": payload.get("email"),
                "label": payload.get("label"),
                "criteria": Json(payload["criteria"]),
            },
        )
        row = cur.fetchone()
    conn.commit()
    return row
