from fastapi import APIRouter

from app.deps import ConnDep
from app.queries import insert_alert
from app.schemas import AlertCreate, AlertOut

router = APIRouter(tags=["alerts"])


@router.post("/alerts", response_model=AlertOut)
def create_alert(payload: AlertCreate, conn: ConnDep) -> AlertOut:
    row = insert_alert(conn, payload.model_dump())
    return AlertOut.model_validate(row)
