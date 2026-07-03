"""Search incentive ranking and filtering — unit tests + optional DB integration."""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.search_service import enrich_and_rank_search, incentive_fields_for_hit

client = TestClient(app)

B1 = str(uuid4())
B2 = str(uuid4())
B3 = str(uuid4())


def _row(building_id: str, name: str, **kwargs) -> dict:
    return {
        "building_id": building_id,
        "listing_id": str(uuid4()),
        "name": name,
        "city": "DC",
        "neighborhood": None,
        "dmv_area": "DC",
        "bedrooms": Decimal("1"),
        "base_rent_monthly": Decimal("2400"),
        "effective_rent_monthly": Decimal("2400"),
        "deal_signal": "fair",
        "has_concession": False,
        "has_fees": False,
        **kwargs,
    }


def _inc(building_id: str, *, free_months: float, savings: int, eff: int, discount: float) -> dict:
    return {
        "id": uuid4(),
        "building_id": building_id,
        "incentive_type": "free_months",
        "free_months": free_months,
        "lease_term_months": 16,
        "listed_rent": 2400,
        "raw_text": f"{free_months:g} months free",
        "total_savings": savings,
        "estimated_savings": savings,
        "effective_rent": eff,
        "all_in_effective_rent": eff,
        "discount_percent": discount,
        "confidence_score": 0.9,
        "is_demo": True,
    }


def test_sort_savings_ranks_highest_savings_first():
    rows = [
        _row(B1, "Alpha"),
        _row(B2, "Beta"),
        _row(B3, "Gamma"),
    ]
    incentives = {
        B1: _inc(B1, free_months=1, savings=2000, eff=2200, discount=10.0),
        B2: _inc(B2, free_months=4, savings=9600, eff=1800, discount=25.0),
        B3: _inc(B3, free_months=2, savings=5000, eff=2000, discount=15.0),
    }
    out = enrich_and_rank_search(rows, incentives, sort="savings")
    names = [r["name"] for r in out]
    assert names[0] == "Beta"
    assert names[1] == "Gamma"
    assert names[2] == "Alpha"


def test_min_free_months_filter():
    rows = [_row(B1, "A"), _row(B2, "B")]
    incentives = {
        B1: _inc(B1, free_months=1, savings=2000, eff=2200, discount=10.0),
        B2: _inc(B2, free_months=3, savings=6000, eff=1900, discount=20.0),
    }
    out = enrich_and_rank_search(rows, incentives, min_free_months=2)
    assert len(out) == 1
    assert out[0]["name"] == "B"
    assert float(out[0]["free_months"]) >= 2


def test_min_savings_filter():
    rows = [_row(B1, "Low"), _row(B2, "High")]
    incentives = {
        B1: _inc(B1, free_months=1, savings=2000, eff=2200, discount=10.0),
        B2: _inc(B2, free_months=3, savings=6000, eff=1900, discount=20.0),
    }
    out = enrich_and_rank_search(rows, incentives, min_savings=5000)
    assert len(out) == 1
    assert out[0]["name"] == "High"
    assert out[0]["estimated_savings"] >= 5000


def test_has_incentive_only_returns_incentive_backed():
    rows = [_row(B1, "With"), _row(B2, "Without")]
    incentives = {B1: _inc(B1, free_months=2, savings=4000, eff=2000, discount=15.0)}
    out = enrich_and_rank_search(rows, incentives, has_incentive=True)
    assert len(out) == 1
    assert out[0]["name"] == "With"
    assert out[0]["best_incentive_id"] is not None


def test_no_incentive_filters_returns_all_rows():
    rows = [_row(B1, "A"), _row(B2, "B")]
    out = enrich_and_rank_search(rows, {}, sort="default")
    assert len(out) == 2
    assert out[0].get("best_incentive_id") is None


def test_incentive_fields_for_hit_maps_keys():
    inc = _inc(B1, free_months=4, savings=9600, eff=1800, discount=25.0)
    fields = incentive_fields_for_hit(inc)
    assert fields["estimated_savings"] == 9600
    assert fields["effective_rent"] == 1800
    assert fields["discount_percent"] == 25.0
    assert fields["incentive_is_demo"] is True


@pytest.mark.db
def test_search_sort_savings_api():
    r = client.get("/search", params={"sort": "savings"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    with_savings = [h for h in data if h.get("estimated_savings") is not None]
    assert len(with_savings) >= 2
    savings = [h["estimated_savings"] for h in with_savings]
    assert savings == sorted(savings, reverse=True)


@pytest.mark.db
def test_search_has_incentive_api():
    r = client.get("/search", params={"has_incentive": True})
    assert r.status_code == 200
    for hit in r.json():
        assert hit.get("best_incentive_id") is not None


@pytest.mark.db
def test_search_without_filters_returns_results():
    r = client.get("/search")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
