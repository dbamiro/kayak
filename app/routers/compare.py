from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.deps import ConnDep
from app.deps_auth import OptionalUser
from app.queries import compare_buildings
from app.schemas import CompareRequest, CompareRow
from app.services.entitlement_service import EntitlementService

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=list[CompareRow])
def compare(req: CompareRequest, conn: ConnDep, user: OptionalUser) -> list[CompareRow]:
    settings = get_settings()
    n = len(req.building_ids)
    if n < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "need_at_least_two_buildings")

    EntitlementService.expire_old_entitlements(conn)
    paid = bool(user and EntitlementService.has_paid_subscription(conn, user.id))
    limit = settings.paid_compare_limit if paid else settings.free_compare_limit
    if n > limit:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"compare_limit_exceeded: max {limit} buildings for your plan",
        )

    rows = compare_buildings(conn, building_ids=req.building_ids, bedrooms_min=req.bedrooms_min)
    out: list[CompareRow] = []
    for r in rows:
        d = dict(r)
        if not paid:
            d["negotiation_score"] = None
            d["leasing_pressure_score"] = None
        out.append(CompareRow.model_validate(d))
    return out
