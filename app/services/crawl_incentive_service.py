"""Persist parser-derived incentives from crawl concession / fee text."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Json

from app.services.incentive_calculator import IncentiveCalculation, calculate_effective_rent
from app.services.incentive_service import merge_parsed_into_data
from app.services.incentive_text_parser import ParsedIncentive, parse_incentive_text

logger = logging.getLogger(__name__)

CRAWLER_CAPTURE_METHOD = "crawler"
CRAWLER_STATUS = "pending_review"
ADMIN_MIN_CONFIDENCE = 0.85
CRAWLER_MAX_CONFIDENCE = 0.74


def is_incentive_parseable(parsed: ParsedIncentive) -> bool:
    if parsed.incentive_type and parsed.incentive_type != "unknown":
        return True
    return any(
        getattr(parsed, field) not in (None, 0)
        for field in (
            "free_months",
            "waived_fee_amount",
            "gift_card_amount",
            "parking_discount_monthly",
            "custom_credit_amount",
        )
    )


def crawler_confidence_score(
    parsed: ParsedIncentive,
    parser_confidence: float | None,
) -> float:
    """Automated crawl confidence — always below admin-verified floor (0.85)."""
    score = float(parsed.confidence_score or 0.5)
    if parser_confidence is not None:
        score *= float(parser_confidence)
    score *= 0.95
    return min(max(score, 0.1), CRAWLER_MAX_CONFIDENCE)


def parse_crawl_incentive_texts(
    concession_text: str | None,
    fee_text: str | None,
) -> ParsedIncentive | None:
    """Pick the highest-confidence parse from concession and fee copy."""
    best: ParsedIncentive | None = None
    for text in (concession_text, fee_text):
        if not text or not str(text).strip():
            continue
        try:
            parsed = parse_incentive_text(str(text))
        except Exception:
            logger.debug("incentive_text_parse_failed", exc_info=True)
            continue
        if not is_incentive_parseable(parsed):
            continue
        if best is None or parsed.confidence_score > best.confidence_score:
            best = parsed
    return best


def concession_dict_from_text(raw_text: str) -> dict[str, Any]:
    """Map marketing copy into normalize/rents concession shapes for listing snapshots."""
    structured: dict[str, Any] = {"raw_text": raw_text}
    try:
        parsed = parse_incentive_text(raw_text)
    except Exception:
        return structured
    if parsed.incentive_type == "free_months" and parsed.free_months:
        months = max(int(round(float(parsed.free_months))), 1)
        structured.update({"type": "percent_off", "percent": 100, "months": months})
    elif parsed.incentive_type == "free_weeks" and parsed.weeks_free:
        weeks = max(int(round(float(parsed.weeks_free))), 1)
        structured.update({"type": "weeks_free", "weeks": weeks})
    return structured


def _find_crawler_incentive(
    conn: Connection,
    *,
    building_id: UUID,
    source_url: str | None,
) -> UUID | None:
    row = conn.execute(
        """
        SELECT id FROM incentives
        WHERE building_id = %s
          AND capture_method = %s
          AND is_demo = false
          AND COALESCE(source_url, '') = COALESCE(%s, '')
          AND COALESCE(status, 'active') NOT IN ('rejected', 'expired')
        ORDER BY updated_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        (str(building_id), CRAWLER_CAPTURE_METHOD, source_url),
    ).fetchone()
    return UUID(str(row[0])) if row else None


def _record_incentive_source(
    conn: Connection,
    *,
    building_id: UUID,
    source_url: str | None,
    incentive_type: str,
    status: str,
) -> None:
    if not source_url:
        return
    updated = conn.execute(
        """
        UPDATE incentive_sources
        SET last_checked_at = now(),
            last_status = %s,
            source_type = COALESCE(source_type, %s),
            updated_at = now()
        WHERE building_id = %s
          AND source_url = %s
          AND capture_method = %s
        RETURNING id
        """,
        (status, incentive_type, str(building_id), source_url, CRAWLER_CAPTURE_METHOD),
    ).fetchone()
    if updated:
        return
    conn.execute(
        """
        INSERT INTO incentive_sources (
            building_id, source_url, source_type, capture_method, active, last_checked_at, last_status
        ) VALUES (%s, %s, %s, %s, true, now(), %s)
        """,
        (str(building_id), source_url, incentive_type, CRAWLER_CAPTURE_METHOD, status),
    )


def persist_crawled_incentive(
    conn: Connection,
    *,
    building_id: UUID,
    listing_id: UUID,
    listing_snapshot_id: UUID,
    concession_text: str | None,
    fee_text: str | None,
    listed_rent: int,
    lease_term_months: int,
    source_url: str,
    parser_name: str | None = None,
    parser_confidence: float | None = None,
) -> UUID | None:
    """
    Parse crawl concession/fee text and append incentive history.

    Returns incentive id when structured data was stored; None when text is unparseable.
    Never raises — crawl persistence must not fail the listing write.
    """
    try:
        parsed = parse_crawl_incentive_texts(concession_text, fee_text)
        if parsed is None:
            return None

        raw_text = (concession_text or fee_text or "").strip()
        if concession_text and fee_text and concession_text.strip() and fee_text.strip():
            raw_text = f"{concession_text.strip()} | {fee_text.strip()}"

        confidence = crawler_confidence_score(parsed, parser_confidence)
        data = merge_parsed_into_data(
            {
                "building_id": building_id,
                "submitted_listing_id": listing_id,
                "source_url": source_url,
                "listed_rent": listed_rent,
                "lease_term_months": lease_term_months,
                "raw_text": raw_text,
                "incentive_type": parsed.incentive_type,
                "capture_method": CRAWLER_CAPTURE_METHOD,
                "verification_method": "parser_derived",
                "confidence_score": confidence,
                "is_demo": False,
                "status": CRAWLER_STATUS,
                "metadata": {
                    "listing_snapshot_id": str(listing_snapshot_id),
                    "parser_name": parser_name,
                    "parser_confidence": parser_confidence,
                },
            },
            parsed,
        )
        if data.get("incentive_type") == "unknown":
            data["incentive_type"] = parsed.incentive_type

        calc: IncentiveCalculation | None = None
        if listed_rent and lease_term_months:
            calc = calculate_effective_rent(
                listed_rent,
                lease_term_months,
                float(data.get("free_months") or 0),
                waived_fee_amount=int(data.get("waived_fee_amount") or 0),
                gift_card_amount=int(data.get("gift_card_amount") or 0),
                parking_discount_monthly=int(data.get("parking_discount_monthly") or 0),
                custom_credit_amount=int(data.get("custom_credit_amount") or 0),
            )

        existing_id = _find_crawler_incentive(conn, building_id=building_id, source_url=source_url)
        if existing_id:
            conn.execute(
                """
                UPDATE incentives SET
                    submitted_listing_id = %(submitted_listing_id)s,
                    incentive_type = %(incentive_type)s,
                    free_months = %(free_months)s,
                    lease_term_months = %(lease_term_months)s,
                    listed_rent = %(listed_rent)s,
                    waived_fee_amount = %(waived_fee_amount)s,
                    gift_card_amount = %(gift_card_amount)s,
                    parking_discount_monthly = %(parking_discount_monthly)s,
                    custom_credit_amount = %(custom_credit_amount)s,
                    raw_text = %(raw_text)s,
                    confidence_score = %(confidence_score)s,
                    status = %(status)s,
                    metadata = %(metadata)s::jsonb,
                    updated_at = now()
                WHERE id = %(id)s
                """,
                {
                    "id": str(existing_id),
                    "submitted_listing_id": str(listing_id),
                    "incentive_type": data["incentive_type"],
                    "free_months": data.get("free_months"),
                    "lease_term_months": lease_term_months,
                    "listed_rent": listed_rent,
                    "waived_fee_amount": int(data.get("waived_fee_amount") or 0),
                    "gift_card_amount": int(data.get("gift_card_amount") or 0),
                    "parking_discount_monthly": int(data.get("parking_discount_monthly") or 0),
                    "custom_credit_amount": int(data.get("custom_credit_amount") or 0),
                    "raw_text": raw_text,
                    "confidence_score": confidence,
                    "status": CRAWLER_STATUS,
                    "metadata": Json(data.get("metadata") or {}),
                },
            )
            incentive_id = existing_id
        else:
            row = conn.execute(
                """
                INSERT INTO incentives (
                    building_id, submitted_listing_id, source_url, incentive_type, free_months,
                    lease_term_months, listed_rent, waived_fee_amount, gift_card_amount,
                    parking_discount_monthly, custom_credit_amount, raw_text,
                    verification_method, capture_method, confidence_score, is_demo, status, metadata
                ) VALUES (
                    %(building_id)s, %(submitted_listing_id)s, %(source_url)s, %(incentive_type)s,
                    %(free_months)s, %(lease_term_months)s, %(listed_rent)s, %(waived_fee_amount)s,
                    %(gift_card_amount)s, %(parking_discount_monthly)s, %(custom_credit_amount)s,
                    %(raw_text)s, %(verification_method)s, %(capture_method)s, %(confidence_score)s,
                    %(is_demo)s, %(status)s, %(metadata)s::jsonb
                )
                RETURNING id
                """,
                {
                    "building_id": str(building_id),
                    "submitted_listing_id": str(listing_id),
                    "source_url": source_url,
                    "incentive_type": data["incentive_type"],
                    "free_months": data.get("free_months"),
                    "lease_term_months": lease_term_months,
                    "listed_rent": listed_rent,
                    "waived_fee_amount": int(data.get("waived_fee_amount") or 0),
                    "gift_card_amount": int(data.get("gift_card_amount") or 0),
                    "parking_discount_monthly": int(data.get("parking_discount_monthly") or 0),
                    "custom_credit_amount": int(data.get("custom_credit_amount") or 0),
                    "raw_text": raw_text,
                    "verification_method": "parser_derived",
                    "capture_method": CRAWLER_CAPTURE_METHOD,
                    "confidence_score": confidence,
                    "is_demo": False,
                    "status": CRAWLER_STATUS,
                    "metadata": Json(data.get("metadata") or {}),
                },
            ).fetchone()
            incentive_id = UUID(str(row[0]))

        if calc:
            conn.execute(
                """
                INSERT INTO incentive_snapshots (
                    incentive_id, raw_text, free_months, lease_term_months, listed_rent,
                    estimated_savings, effective_rent, all_in_effective_rent, confidence_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(incentive_id),
                    raw_text,
                    data.get("free_months"),
                    lease_term_months,
                    listed_rent,
                    calc.total_savings,
                    calc.effective_rent,
                    calc.all_in_effective_rent,
                    confidence,
                ),
            )

        _record_incentive_source(
            conn,
            building_id=building_id,
            source_url=source_url,
            incentive_type=str(data["incentive_type"]),
            status="parsed",
        )
        return incentive_id
    except Exception:
        logger.exception(
            "persist_crawled_incentive_failed building_id=%s listing_id=%s",
            building_id,
            listing_id,
        )
        return None
