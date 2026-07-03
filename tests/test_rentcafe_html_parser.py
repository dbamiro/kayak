"""RentCafe / Yardi DOM parser tests (fixture only, no network)."""

from __future__ import annotations

from pathlib import Path

from parsers.rentcafe_html_parser import RentcafeHtmlParser

FIXTURE = Path(__file__).parent / "fixtures" / "dominion_b1a_sample.html"
URL = "https://www.dominionapts.com/floorplans/b1a"


def test_can_parse_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    parser = RentcafeHtmlParser()
    assert parser.can_parse(html, URL) is True


def test_parse_fixture_extracts_listings():
    html = FIXTURE.read_text(encoding="utf-8")
    parser = RentcafeHtmlParser()
    rows = parser.parse(html, URL, {})
    assert len(rows) >= 2

    units = {r.unit_label for r in rows}
    assert "617" in units
    assert "626" in units

    by_unit = {r.unit_label: r for r in rows}
    assert by_unit["617"].listed_rent_min == 2200
    assert by_unit["626"].listed_rent_min == 2150
    assert by_unit["617"].listed_rent_max == 2200

    sample = by_unit["617"]
    assert sample.floorplan_name == "B1A"
    assert sample.bedrooms == 2.0
    assert sample.bathrooms == 1.0
    assert sample.sqft == 890
    assert sample.concession_text is not None
    assert "one month free" in sample.concession_text.lower()
    assert sample.parser_name.startswith("rentcafe_html")
    assert sample.confidence_score >= 0.7


def test_parse_empty_html_returns_empty():
    parser = RentcafeHtmlParser()
    assert parser.parse("<html><body></body></html>", URL, {}) == []
