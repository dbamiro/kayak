from decimal import Decimal

from fastapi import APIRouter, Query

from app.deps import ConnDep
from app.schemas import SearchHit
from app.services.search_service import SearchSort, search_listings_with_incentives

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
    sort: SearchSort = Query(
        "default",
        description="default | savings | effective_rent | discount",
    ),
    min_free_months: float | None = Query(None, ge=0, description="Require incentive free_months >= value"),
    min_savings: int | None = Query(None, ge=0, description="Require incentive estimated_savings >= value"),
    max_effective_rent: int | None = Query(None, ge=0, description="Require incentive effective_rent <= value"),
    has_incentive: bool | None = Query(None, description="Only buildings with a tracked special"),
    include_demo: bool | None = Query(
        None,
        description="Include demo incentives (default from SHOW_DEMO_DATA env)",
    ),
) -> list[SearchHit]:
    rows = search_listings_with_incentives(
        conn,
        city=city,
        dmv_area=dmv_area,
        min_rent=min_rent,
        max_rent=max_rent,
        bedrooms_min=bedrooms_min,
        sort=sort,
        min_free_months=min_free_months,
        min_savings=min_savings,
        max_effective_rent=max_effective_rent,
        has_incentive=has_incentive,
        include_demo=include_demo,
    )
    return [SearchHit.model_validate(r) for r in rows]
