"""Incentive discovery API — specials, effective rent, savings."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.deps import ConnDep
from app.deps_auth import OptionalUser
from app.schemas import (
    IncentiveCalculateBody,
    IncentiveCalculationOut,
    IncentiveCardOut,
    IncentiveParseBody,
    IncentiveParseOut,
    IncentiveSubmitBody,
)
from app.services.demo_policy import resolve_include_demo
from app.services.incentive_calculator import calculate_effective_rent
from app.services.incentive_service import (
    create_incentive,
    get_incentive,
    list_incentives_ranked,
    merge_parsed_into_data,
    parse_and_calculate,
    resolve_building_id,
)
from app.services.incentive_text_parser import parse_incentive_text
from app.abuse_validation import validate_optional_url, validate_submission_text
from app.rate_limit import check_duplicate_submission, check_incentive_submit_limit

router = APIRouter(prefix="/incentives", tags=["incentives"])


@router.get("", response_model=list[IncentiveCardOut])
def list_incentives(
    conn: ConnDep,
    building_id: UUID | None = None,
    city: str | None = None,
    dmv_area: str | None = None,
    neighborhood: str | None = None,
    min_free_months: float | None = Query(None, ge=0),
    min_savings: int | None = Query(None, ge=0),
    bedrooms: float | None = None,
    max_effective_rent: int | None = Query(None, ge=0),
    include_demo: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[IncentiveCardOut]:
    rows = list_incentives_ranked(
        conn,
        building_id=building_id,
        city=city,
        dmv_area=dmv_area,
        neighborhood=neighborhood,
        min_free_months=min_free_months,
        min_savings=min_savings,
        bedrooms=bedrooms,
        max_effective_rent=max_effective_rent,
        include_demo=resolve_include_demo(include_demo),
        limit=limit,
    )
    return [IncentiveCardOut.model_validate(r) for r in rows]


@router.get("/{incentive_id}", response_model=IncentiveCardOut)
def get_incentive_detail(conn: ConnDep, incentive_id: UUID) -> IncentiveCardOut:
    row = get_incentive(conn, incentive_id)
    if not row:
        raise HTTPException(404, "incentive_not_found")
    return IncentiveCardOut.model_validate(row)


@router.post("/calculate", response_model=IncentiveCalculationOut)
def post_calculate(body: IncentiveCalculateBody) -> IncentiveCalculationOut:
    calc = calculate_effective_rent(
        body.listed_rent,
        body.lease_term_months,
        body.free_months,
        recurring_fee_monthly=body.recurring_fee_monthly,
        one_time_fee=body.one_time_fee,
        waived_fee_amount=body.waived_fee_amount,
        gift_card_amount=body.gift_card_amount,
        parking_discount_monthly=body.parking_discount_monthly,
        custom_credit_amount=body.custom_credit_amount,
    )
    return IncentiveCalculationOut.model_validate(calc.__dict__)


@router.post("/parse", response_model=IncentiveParseOut)
def post_parse(body: IncentiveParseBody) -> IncentiveParseOut:
    result = parse_and_calculate(body.raw_text, body.listed_rent, body.lease_term_months)
    calc = result.get("calculation")
    return IncentiveParseOut(
        parsed=result["parsed"],
        calculation=IncentiveCalculationOut.model_validate(calc) if calc else None,
    )


@router.post("/submit", response_model=IncentiveCardOut, status_code=201)
def submit_incentive(
    conn: ConnDep,
    body: IncentiveSubmitBody,
    request: Request,
    user: OptionalUser = None,
) -> IncentiveCardOut:
    check_incentive_submit_limit(request)
    raw_text = validate_submission_text(body.raw_special_text, field="raw_special_text")
    check_duplicate_submission(request, raw_text)
    source_url = validate_optional_url(body.source_url, field="source_url")
    screenshot_url = validate_optional_url(body.screenshot_url, field="screenshot_url")

    parsed = parse_incentive_text(raw_text)
    building_id = body.building_id
    if not building_id and body.building_name:
        building_id = resolve_building_id(conn, building_name=body.building_name, city=body.city)

    listed = body.rent
    term = body.lease_term_months or 12
    if not listed or not term:
        raise HTTPException(400, "rent and lease_term_months required to store submission")

    data = merge_parsed_into_data(
        {
            "building_id": building_id,
            "source_url": source_url or screenshot_url,
            "lease_term_months": term,
            "listed_rent": listed,
            "raw_text": raw_text,
            "applies_to": body.applies_to,
            "confidence_score": min(parsed.confidence_score, 0.55),
            "is_demo": False,
            "status": "pending_review",
            "verification_method": "user_submitted",
            "capture_method": "user_submission",
            "submitted_by_user_id": user.id if user else None,
            "metadata": {
                "submitted": True,
                "city": body.city,
                "neighborhood": body.neighborhood,
                "screenshot_url": screenshot_url,
                "submitted_by_email": user.email if user else None,
            },
        },
        parsed,
    )
    if not data.get("incentive_type") or data["incentive_type"] == "unknown":
        data["incentive_type"] = parsed.incentive_type if parsed.incentive_type != "unknown" else "user_submitted"

    row = create_incentive(conn, data)
    return IncentiveCardOut.model_validate(row)
