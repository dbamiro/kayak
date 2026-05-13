from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.deps import ConnDep
from app.queries import get_building, list_building_quotes, listing_history
from app.schemas import BuildingDetail, ListingQuote, SnapshotPoint

router = APIRouter(tags=["buildings"])


@router.get("/buildings/{building_id}", response_model=dict)
def building_detail(building_id: UUID, conn: ConnDep) -> dict:
    row = get_building(conn, building_id)
    if not row:
        raise HTTPException(status_code=404, detail="Building not found")
    quotes = list_building_quotes(conn, building_id)
    return {
        "building": BuildingDetail.model_validate(row).model_dump(),
        "listings": [ListingQuote.model_validate(q).model_dump() for q in quotes],
    }


@router.get("/buildings/{building_id}/history")
def building_history(building_id: UUID, conn: ConnDep) -> dict:
    if not get_building(conn, building_id):
        raise HTTPException(status_code=404, detail="Building not found")
    rows = listing_history(conn, building_id)
    series: dict[str, list[SnapshotPoint]] = {}
    meta: dict[str, str | None] = {}
    for r in rows:
        lid = str(r["listing_id"])
        meta.setdefault(lid, r.get("floorplan_name"))
        pt = SnapshotPoint.model_validate(
            {
                "captured_at": r["captured_at"],
                "base_rent_monthly": r["base_rent_monthly"],
                "effective_rent_monthly": r["effective_rent_monthly"],
                "all_in_monthly": r["all_in_monthly"],
                "leasing_pressure_score": r["leasing_pressure_score"],
                "negotiation_score": r["negotiation_score"],
            }
        )
        series.setdefault(lid, []).append(pt)
    return {"building_id": str(building_id), "series": series, "floorplans": meta}
