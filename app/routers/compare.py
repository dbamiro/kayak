from fastapi import APIRouter

from app.deps import ConnDep
from app.queries import compare_buildings
from app.schemas import CompareRequest, CompareRow

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=list[CompareRow])
def compare(req: CompareRequest, conn: ConnDep) -> list[CompareRow]:
    rows = compare_buildings(conn, building_ids=req.building_ids, bedrooms_min=req.bedrooms_min)
    return [CompareRow.model_validate(r) for r in rows]
