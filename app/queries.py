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
            b.id AS building_id,
            b.name,
            b.city,
            b.neighborhood,
            b.dmv_area::text AS dmv_area,
            l.id AS listing_id,
            l.bedrooms,
            ls.base_rent_monthly,
            ls.effective_rent_monthly,
            ls.all_in_monthly,
            ls.leasing_pressure_score,
            ls.negotiation_score,
            ls.captured_at AS snapshot_at,
            (ls.concessions IS NOT NULL AND ls.concessions::text NOT IN ('{}', 'null', '{"raw_text": ""}'))
                AS has_concession,
            (ls.fees IS NOT NULL AND ls.fees::text NOT IN ('{}', 'null', '{"raw_text": ""}'))
                AS has_fees,
            CASE
                WHEN ls.negotiation_score IS NULL THEN 'fair'
                WHEN ls.negotiation_score >= 65 THEN 'strong'
                WHEN ls.negotiation_score >= 45 THEN 'fair'
                ELSE 'weak'
            END AS deal_signal
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


def count_active_alerts_for_user(conn: Connection, user_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM alerts WHERE user_id = %s AND active = true",
            (str(user_id),),
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0


def list_alerts_for_user(conn: Connection, user_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, user_id, email, label, name, alert_type, criteria, active, created_at, updated_at
            FROM alerts
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (str(user_id),),
        )
        return [dict(r) for r in cur.fetchall()]


def insert_alert(conn: Connection, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO alerts (user_id, email, label, name, criteria, alert_type, active)
            VALUES (
                %(uid)s,
                %(email)s,
                %(label)s,
                COALESCE(%(name)s, %(label)s),
                %(criteria)s,
                %(atype)s,
                true
            )
            RETURNING id, user_id, email, label, name, alert_type, criteria, active, created_at, updated_at
            """,
            {
                "uid": str(user_id),
                "email": payload.get("email"),
                "label": payload.get("label"),
                "name": payload.get("name"),
                "criteria": Json(payload["criteria"]),
                "atype": payload.get("alert_type", "general"),
            },
        )
        row = cur.fetchone()
    conn.commit()
    return row


def update_alert(conn: Connection, user_id: UUID, alert_id: UUID, patch: dict[str, Any]) -> dict[str, Any] | None:
    fields: list[str] = []
    params: dict[str, Any] = {"uid": str(user_id), "aid": str(alert_id)}
    if "name" in patch and patch["name"] is not None:
        fields.append("name = %(name)s")
        params["name"] = patch["name"]
    if "label" in patch and patch["label"] is not None:
        fields.append("label = %(label)s")
        params["label"] = patch["label"]
    if "criteria" in patch and patch["criteria"] is not None:
        fields.append("criteria = %(criteria)s")
        params["criteria"] = Json(patch["criteria"])
    if "alert_type" in patch and patch["alert_type"] is not None:
        fields.append("alert_type = %(atype)s")
        params["atype"] = patch["alert_type"]
    if "active" in patch and patch["active"] is not None:
        fields.append("active = %(active)s")
        params["active"] = patch["active"]
    if not fields:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, email, label, name, alert_type, criteria, active, created_at, updated_at
                FROM alerts WHERE id = %(aid)s AND user_id = %(uid)s
                """,
                params,
            )
            return cur.fetchone()
    fields.append("updated_at = now()")
    sql = f"""
        UPDATE alerts SET {", ".join(fields)}
        WHERE id = %(aid)s AND user_id = %(uid)s
        RETURNING id, user_id, email, label, name, alert_type, criteria, active, created_at, updated_at
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    conn.commit()
    return row


def delete_alert(conn: Connection, user_id: UUID, alert_id: UUID) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM alerts WHERE id = %s AND user_id = %s", (str(alert_id), str(user_id)))
        n = cur.rowcount or 0
    conn.commit()
    return n > 0
