from decimal import Decimal

from fastapi import APIRouter, Query

from app.deps import ConnDep
from app.queries import search_buildings
from app.schemas import SearchHit

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[SearchHit])
def search_listings(
    conn: ConnDep,
    city: str | None = Query(None, description="Substring match on city name"),
    dmv_area: str | None = Query(
        None,
        description="Exact enum label: DC, ARLINGTON, ALEXANDRIA, TYSONS, RESTON, ASHBURN, SILVER_SPRING, BETHESDA",
    ),
    min_rent: Decimal | None = Query(None, ge=0),
    max_rent: Decimal | None = Query(None, ge=0),
    bedrooms_min: Decimal | None = Query(None, ge=0),
) -> list[SearchHit]:
    rows = search_buildings(
        conn,
        city=city,
        dmv_area=dmv_area,
        min_rent=min_rent,
        max_rent=max_rent,
        bedrooms_min=bedrooms_min,
    )
    return [SearchHit.model_validate(r) for r in rows]
