"""Crawl concession text → structured incentive persistence."""

from __future__ import annotations

from uuid import UUID

import pytest
from psycopg.rows import dict_row

from app.services.crawl_incentive_service import (
    CRAWLER_CAPTURE_METHOD,
    CRAWLER_MAX_CONFIDENCE,
    ADMIN_MIN_CONFIDENCE,
    concession_dict_from_text,
    crawler_confidence_score,
    is_incentive_parseable,
    parse_crawl_incentive_texts,
    persist_crawled_incentive,
)
from app.services.incentive_text_parser import parse_incentive_text
from crawler.writer import persist_canonical_listing
from models.canonical_listing import CanonicalListing

TEST_BUILDING_ID = UUID("b0000000-0000-4000-8000-000000000001")


def _crawler_incentives(conn, building_id: UUID = TEST_BUILDING_ID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT i.*, (
                SELECT count(*) FROM incentive_snapshots s WHERE s.incentive_id = i.id
            ) AS snapshot_count
            FROM incentives i
            WHERE i.building_id = %s AND i.capture_method = %s
            ORDER BY i.created_at
            """,
            (str(building_id), CRAWLER_CAPTURE_METHOD),
        )
        return [dict(r) for r in cur.fetchall()]


def _persist_listing(
    conn,
    *,
    concession_text: str | None = None,
    fee_text: str | None = None,
    rent: int = 2400,
    source_url: str = "https://example.com/crawl-incentive-test",
) -> None:
    cl = CanonicalListing(
        floorplan_name="Crawl Test 1BR",
        unit_label="CT-101",
        bedrooms=1,
        listed_rent_min=rent,
        concession_text=concession_text,
        fee_text=fee_text,
        source_url=source_url,
        parser_name="test_parser",
        confidence_score=0.9,
    )
    persist_canonical_listing(
        conn,
        building_id=TEST_BUILDING_ID,
        raw_document_id=None,
        canonical=cl,
    )


# --- unit tests (no DB) ---


def test_crawler_confidence_below_admin_verified():
    parsed = parse_incentive_text("2 months free")
    score = crawler_confidence_score(parsed, parser_confidence=0.95)
    assert score <= CRAWLER_MAX_CONFIDENCE
    assert score < ADMIN_MIN_CONFIDENCE


def test_unparseable_marketing_copy_skipped():
    assert parse_crawl_incentive_texts("Luxury living in the heart of the city", None) is None
    assert not is_incentive_parseable(parse_incentive_text("Luxury living awaits"))


def test_concession_dict_maps_free_months():
    d = concession_dict_from_text("2 months free on select homes")
    assert d["type"] == "percent_off"
    assert d["months"] == 2
    assert "raw_text" in d


# --- DB integration ---


@pytest.mark.db
@pytest.mark.parametrize(
    "text,expected_type,field,expected_value",
    [
        ("2 months free on 12-month leases", "free_months", "free_months", 2.0),
        ("6 weeks free when you sign today", "free_weeks", "free_months", None),
        ("$1,500 move-in credit for new residents", "rent_credit", "custom_credit_amount", 1500),
        ("Limited time waived admin fee", "waived_admin_fee", "waived_fee_amount", 500),
    ],
)
def test_crawl_persists_parsed_incentive_types(
    conn,
    text: str,
    expected_type: str,
    field: str,
    expected_value: float | int | None,
) -> None:
    _persist_listing(conn, concession_text=text)

    rows = _crawler_incentives(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["incentive_type"] == expected_type
    assert row["is_demo"] is False
    assert row["capture_method"] == CRAWLER_CAPTURE_METHOD
    assert row["status"] == "pending_review"
    assert row["verification_method"] == "parser_derived"
    assert float(row["confidence_score"]) < ADMIN_MIN_CONFIDENCE
    assert row["snapshot_count"] == 1

    if field == "free_months" and expected_type == "free_weeks":
        assert row["free_months"] is not None and float(row["free_months"]) > 0
    elif expected_value is not None:
        assert float(row[field]) == float(expected_value)


@pytest.mark.db
def test_unparseable_crawl_text_does_not_create_incentive(conn) -> None:
    before = len(_crawler_incentives(conn))
    _persist_listing(conn, concession_text="Experience boutique urban living at its finest")
    after = len(_crawler_incentives(conn))
    assert after == before


@pytest.mark.db
def test_crawl_incentive_append_only_snapshots(conn) -> None:
    source = "https://example.com/crawl-append-test"
    _persist_listing(conn, concession_text="1 month free", source_url=source)
    _persist_listing(conn, concession_text="2 months free", source_url=source)

    rows = _crawler_incentives(conn)
    assert len(rows) == 1
    assert rows[0]["free_months"] == 2
    assert rows[0]["snapshot_count"] == 2


@pytest.mark.db
def test_fee_text_waived_admin_persisted(conn) -> None:
    _persist_listing(conn, fee_text="Waived application fee for a limited time")
    rows = _crawler_incentives(conn)
    assert len(rows) == 1
    assert rows[0]["incentive_type"] == "waived_application_fee"
    assert int(rows[0]["waived_fee_amount"]) == 75


@pytest.mark.db
def test_persist_crawled_incentive_never_raises_on_bad_input(conn) -> None:
    listing_id = conn.execute(
        "SELECT id FROM listings WHERE building_id = %s LIMIT 1",
        (str(TEST_BUILDING_ID),),
    ).fetchone()[0]
    snap_id = conn.execute(
        "SELECT id FROM listing_snapshots WHERE listing_id = %s LIMIT 1",
        (str(listing_id),),
    ).fetchone()[0]

    result = persist_crawled_incentive(
        conn,
        building_id=TEST_BUILDING_ID,
        listing_id=UUID(str(listing_id)),
        listing_snapshot_id=UUID(str(snap_id)),
        concession_text="not a real parse \x00 broken",
        fee_text=None,
        listed_rent=0,
        lease_term_months=12,
        source_url="https://example.com/bad",
        parser_name="test",
        parser_confidence=None,
    )
    assert result is None
