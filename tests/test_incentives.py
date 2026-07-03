"""Incentive calculator, parser, and API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.incentive_calculator import calculate_effective_rent, weeks_free_to_months
from app.services.incentive_text_parser import parse_incentive_text

client = TestClient(app)


def test_four_months_free_calculation():
    c = calculate_effective_rent(2400, 16, 4)
    assert c.gross_rent_total == 38400
    assert c.concession_value == 9600
    assert c.total_savings == 9600
    assert c.effective_rent == 1800
    assert c.discount_percent == 25.0


def test_six_weeks_free_parsing():
    p = parse_incentive_text("Apply today — 6 weeks free on 14-month leases")
    assert p.free_months is not None
    assert abs(p.free_months - weeks_free_to_months(6)) < 0.05
    assert p.weeks_free == 6


def test_eight_weeks_free_parsing():
    p = parse_incentive_text("8 weeks free when you lease this month")
    assert p.weeks_free == 8
    assert abs(p.free_months - weeks_free_to_months(8)) < 0.05


def test_five_and_six_months_parsing():
    assert parse_incentive_text("5 months free").free_months == 5.0
    assert parse_incentive_text("six months free").free_months == 6.0


def test_waived_admin_fee_parsing():
    p = parse_incentive_text("Limited time: waived admin fee for new residents")
    assert p.incentive_type == "waived_admin_fee"
    assert p.waived_fee_amount is not None


def test_gift_card_parsing():
    p = parse_incentive_text("Sign today and receive a $1000 gift card")
    assert p.gift_card_amount == 1000


def test_effective_rent_with_fees():
    c = calculate_effective_rent(
        2000,
        12,
        1,
        recurring_fee_monthly=100,
        waived_fee_amount=500,
    )
    assert c.total_savings > 2000
    assert c.effective_rent < 2000


@pytest.mark.db
def test_incentives_list_endpoint():
    r = client.get("/incentives?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_calculate_endpoint():
    r = client.post(
        "/incentives/calculate",
        json={"listed_rent": 2400, "lease_term_months": 16, "free_months": 4},
    )
    assert r.status_code == 200
    assert r.json()["effective_rent"] == 1800


def test_parse_endpoint():
    r = client.post(
        "/incentives/parse",
        json={
            "raw_text": "4 months free on 16 month lease",
            "listed_rent": 2400,
            "lease_term_months": 16,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["parsed"]["free_months"] == 4
    assert body["calculation"]["effective_rent"] == 1800
