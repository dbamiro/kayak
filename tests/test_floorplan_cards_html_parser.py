"""floorplan_cards_html parser and triage diagnostics tests."""

from __future__ import annotations

from pathlib import Path

from crawler.block_detection import is_block_page
from crawler.page_diagnostics import analyze_rendered_html, triage_recommendation
from parsers.floorplan_cards_html_parser import FloorplanCardsHtmlParser

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://example-property.com/floorplans"


def test_floorplan_card_generic_extracts():
    html = (FIXTURES / "floorplan_card_generic.html").read_text(encoding="utf-8")
    parser = FloorplanCardsHtmlParser()
    assert parser.can_parse(html, URL)
    rows = parser.parse(html, URL, {})
    assert len(rows) >= 1
    rents = {r.listed_rent_min for r in rows}
    assert 2100 in rents or 1895 in rents
    assert any(r.bedrooms is not None for r in rows)


def test_unit_card_extracts():
    html = (FIXTURES / "unit_card.html").read_text(encoding="utf-8")
    parser = FloorplanCardsHtmlParser()
    rows = parser.parse(html, URL, {})
    assert len(rows) >= 1
    units = {r.unit_label for r in rows if r.unit_label}
    assert "501" in units or "512" in units


def test_marketing_no_data_empty():
    html = (FIXTURES / "marketing_no_data.html").read_text(encoding="utf-8")
    parser = FloorplanCardsHtmlParser()
    assert parser.can_parse(html, URL) is False
    assert parser.parse(html, URL, {}) == []


def test_cloudflare_fixture_blocked():
    html = (FIXTURES / "cloudflare_block.html").read_text(encoding="utf-8")
    assert is_block_page(html, "https://www.rentcafe.com/x") is True
    diag = analyze_rendered_html(html, "https://www.rentcafe.com/x")
    assert diag["block_page_detected"] is True
    assert triage_recommendation(diag, 0) == "BLOCKED"


def test_diagnostics_rent_snippets_on_card_fixture():
    html = (FIXTURES / "floorplan_card_generic.html").read_text(encoding="utf-8")
    diag = analyze_rendered_html(html, URL)
    assert diag["rendered_html_has_rent_amounts"] is True
    assert diag["rent_like_pattern_count"] >= 1
    assert triage_recommendation(diag, 0) == "NEEDS_HTML_PARSER"
