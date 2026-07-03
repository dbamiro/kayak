"""Saved buildings (shortlist) for authenticated users."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.deps import ConnDep
from app.deps_auth import CurrentUser

router = APIRouter(tags=["saved"])


class SavedBuildingCreate(BaseModel):
    building_id: UUID
    note: str | None = None


@router.get("/saved-buildings")
def list_saved(user: CurrentUser, conn: ConnDep) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT sb.id, sb.building_id, sb.note, sb.created_at,
                   b.name AS building_name, b.city
            FROM saved_buildings sb
            JOIN buildings b ON b.id = sb.building_id
            WHERE sb.user_id = %s
            ORDER BY sb.created_at DESC
            """,
            (str(user.id),),
        )
        return [dict(r) for r in cur.fetchall()]


@router.post("/saved-buildings", status_code=201)
def add_saved(user: CurrentUser, conn: ConnDep, body: SavedBuildingCreate) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id FROM buildings WHERE id = %s", (str(body.building_id),))
        if not cur.fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "building_not_found")
        cur.execute(
            """
            INSERT INTO saved_buildings (user_id, building_id, note)
            VALUES (%(u)s, %(b)s, %(n)s)
            ON CONFLICT (user_id, building_id) DO UPDATE SET note = COALESCE(EXCLUDED.note, saved_buildings.note)
            RETURNING id, building_id, note, created_at
            """,
            {"u": str(user.id), "b": str(body.building_id), "n": body.note},
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return dict(row)


@router.delete("/saved-buildings/{building_id}", status_code=204)
def remove_saved(user: CurrentUser, conn: ConnDep, building_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM saved_buildings WHERE user_id = %s AND building_id = %s",
            (str(user.id), str(building_id)),
        )
    conn.commit()
