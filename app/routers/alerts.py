from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.deps import ConnDep
from app.deps_auth import CurrentUser
from app.queries import (
    count_active_alerts_for_user,
    delete_alert,
    insert_alert,
    list_alerts_for_user,
    update_alert,
)
from app.schemas import AlertCreate, AlertOut, AlertPatch
from app.services.entitlement_service import EntitlementService
from psycopg.rows import dict_row

router = APIRouter(tags=["alerts"])

PAID_ALERT_TYPES = frozenset(
    {
        "new_concession",
        "fee_change",
        "new_matching_listing",
        "deal_score_improved",
        "new_2_month_special",
        "new_3_month_special",
        "new_4_month_special",
        "savings_above_threshold",
        "effective_rent_below_budget",
    }
)


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(user: CurrentUser, conn: ConnDep) -> list[AlertOut]:
    rows = list_alerts_for_user(conn, user.id)
    return [AlertOut.model_validate(r) for r in rows]


@router.post("/alerts", response_model=AlertOut)
def create_alert(user: CurrentUser, conn: ConnDep, payload: AlertCreate) -> AlertOut:
    settings = get_settings()
    EntitlementService.expire_old_entitlements(conn)
    paid = EntitlementService.has_paid_subscription(conn, user.id)
    if not paid and payload.alert_type in PAID_ALERT_TYPES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "advanced_alerts_require_hunt_pass",
        )
    limit = settings.paid_alert_limit if paid else settings.free_alert_limit
    if count_active_alerts_for_user(conn, user.id) >= limit:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"alert_limit_exceeded: max {limit} active alerts",
        )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT email FROM users WHERE id = %s", (str(user.id),))
        u = cur.fetchone()
    email = (u or {}).get("email") or payload.email

    row = insert_alert(
        conn,
        user.id,
        {
            "email": email,
            "label": payload.label,
            "name": payload.name,
            "criteria": payload.criteria,
            "alert_type": payload.alert_type,
        },
    )
    return AlertOut.model_validate(row)


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
def patch_alert(user: CurrentUser, conn: ConnDep, alert_id: UUID, body: AlertPatch) -> AlertOut:
    EntitlementService.expire_old_entitlements(conn)
    paid = EntitlementService.has_paid_subscription(conn, user.id)
    if body.alert_type is not None and not paid and body.alert_type in PAID_ALERT_TYPES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "advanced_alerts_require_hunt_pass")

    patch = body.model_dump(exclude_unset=True)
    row = update_alert(conn, user.id, alert_id, patch)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert_not_found")
    return AlertOut.model_validate(row)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_alert(user: CurrentUser, conn: ConnDep, alert_id: UUID) -> None:
    ok = delete_alert(conn, user.id, alert_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert_not_found")
