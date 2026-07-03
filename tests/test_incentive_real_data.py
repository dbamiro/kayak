"""Real vs demo incentives, parser breadth, and unlimited free-month support."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.incentive_calculator import WEEKS_PER_MONTH, calculate_effective_rent, weeks_free_to_months
from app.services.incentive_text_parser import parse_incentive_text
from app.services.search_service import enrich_and_rank_search

client = TestClient(app)

B1 = str(uuid4())
B2 = str(uuid4())


def _row(bid: str, name: str) -> dict:
    return {
        "building_id": bid,
        "listing_id": str(uuid4()),
        "name": name,
        "city": "DC",
        "neighborhood": None,
        "dmv_area": "DC",
        "bedrooms": None,
        "base_rent_monthly": 2400,
        "deal_signal": "fair",
        "has_concession": False,
        "has_fees": False,
    }


def _inc(bid: str, *, free_months: float, is_demo: bool, savings: int = 5000) -> dict:
    return {
        "id": uuid4(),
        "building_id": bid,
        "incentive_type": "free_months",
        "free_months": free_months,
        "lease_term_months": 16,
        "listed_rent": 2400,
        "raw_text": f"{free_months:g} months free",
        "total_savings": savings,
        "estimated_savings": savings,
        "effective_rent": 1800,
        "discount_percent": 20.0,
        "is_demo": is_demo,
    }


@pytest.mark.parametrize(
    "text,expected_months",
    [
        ("6 weeks free on 14-month lease", 6 / WEEKS_PER_MONTH),
        ("8 weeks free when you sign today", 8 / WEEKS_PER_MONTH),
        ("5 months free on 18 month lease", 5.0),
        ("six months free", 6.0),
        ("1.5 months free", 1.5),
        ("up to 6 months free", 6.0),
    ],
)
def test_parser_months_and_weeks(text: str, expected_months: float):
    p = parse_incentive_text(text)
    assert p.free_months is not None
    assert abs(p.free_months - expected_months) < 0.05


def test_parser_rent_credit():
    p = parse_incentive_text("$1,500 move-in credit")
    assert p.custom_credit_amount == 1500
    assert p.incentive_type == "rent_credit"


def test_weeks_use_4333_divisor():
    assert abs(weeks_free_to_months(8) - 8 / 4.333) < 0.001


def test_calculator_fractional_free_months():
    c = calculate_effective_rent(2400, 16, 1.5)
    assert c.concession_value == 3600
    assert c.effective_rent == 2175


def test_calculator_clamps_free_months_to_lease_term():
    c = calculate_effective_rent(2000, 12, 15, clamp_free_months=True)
    assert c.free_months_applied == 12.0


def test_calculator_custom_credit():
    c = calculate_effective_rent(2400, 16, 0, custom_credit_amount=1500)
    assert c.total_savings == 1500


def test_min_free_months_5_filter():
    rows = [_row(B1, "Five"), _row(B2, "Two")]
    incentives = {
        B1: _inc(B1, free_months=5, is_demo=True, savings=12000),
        B2: _inc(B2, free_months=2, is_demo=True, savings=4000),
    }
    out = enrich_and_rank_search(rows, incentives, min_free_months=5)
    assert len(out) == 1
    assert out[0]["name"] == "Five"


def test_min_free_months_1_5_filter():
    rows = [_row(B1, "High"), _row(B2, "Low")]
    incentives = {
        B1: _inc(B1, free_months=2, is_demo=True),
        B2: _inc(B2, free_months=1, is_demo=True),
    }
    out = enrich_and_rank_search(rows, incentives, min_free_months=1.5)
    assert len(out) == 1
    assert out[0]["name"] == "High"


def test_include_demo_false_excludes_demo_in_enrichment():
    rows = [_row(B1, "DemoOnly")]
    incentives = {B1: _inc(B1, free_months=4, is_demo=True)}
    # Simulate fetch layer: empty when demo excluded
    out = enrich_and_rank_search(rows, {}, has_incentive=True)
    assert len(out) == 0


def test_no_four_month_max_in_parser():
    for months in (5, 6, 8):
        p = parse_incentive_text(f"{months} months free")
        assert p.free_months == float(months)


@pytest.mark.db
def test_search_include_demo_false_api():
    r = client.get("/search", params={"has_incentive": True, "include_demo": False})
    assert r.status_code == 200
    for hit in r.json():
        assert hit.get("incentive_is_demo") is not True


@pytest.mark.db
def test_search_min_free_months_decimal_api():
    r = client.get("/search", params={"min_free_months": 1.5, "include_demo": True})
    assert r.status_code == 200
    assert isinstance(r.json(), list)
