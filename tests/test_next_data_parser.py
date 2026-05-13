"""Lightweight parser unit tests (no network)."""

from __future__ import annotations

import json

from models.canonical_listing import CanonicalListing
from parsers.listing_extract import (
    candidate_to_canonical,
    deep_find_candidate_objects,
    normalize_bathrooms,
    normalize_bedrooms,
    normalize_rent,
)
from parsers.next_data_parser import NextDataParser, extract_next_data_json


def test_extract_next_data_json_present():
    payload = {"props": {"pageProps": {"units": [{"rent": 2100, "bedrooms": 1, "floorPlan": "A"}]}}}
    html = f'<html><head></head><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></body></html>'
    assert extract_next_data_json(html) == payload


def test_extract_next_data_json_missing():
    assert extract_next_data_json("<html></html>") is None


def test_deep_find_candidates():
    tree = {
        "noise": [{"foo": "bar"}],
        "nested": {"items": [{"rent": 1995, "bedrooms": 2, "floorplan": "B2", "baths": 2}]},
    }
    found = deep_find_candidate_objects(tree, min_score=3)
    assert len(found) >= 1
    assert any(f.get("rent") == 1995 for f in found)


def test_normalize_helpers():
    assert normalize_rent("$2,450 / mo") == 2450
    assert normalize_bedrooms("Studio") == 0.0
    assert normalize_bathrooms("2.5 ba") == 2.5


def test_next_data_parser_emits_canonical():
    payload = {
        "props": {
            "pageProps": {
                "inventory": [
                    {
                        "monthlyRent": 2800,
                        "bedrooms": 2,
                        "bathrooms": 2,
                        "squareFeet": 980,
                        "floorPlan": "B2-A",
                        "unitNumber": "412",
                        "availableDate": "2026-06-01",
                        "specials": "$500 look-and-lease",
                        "fees": "amenity $45/mo",
                    }
                ]
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'
    parser = NextDataParser()
    assert parser.can_parse(html, "https://example.com/floorplans")
    rows = parser.parse(html, "https://example.com/floorplans", {})
    assert len(rows) >= 1
    assert isinstance(rows[0], CanonicalListing)
    assert rows[0].listed_rent_min == 2800
    assert rows[0].unit_label == "412"


def test_candidate_to_canonical_safe_when_no_rent():
    assert candidate_to_canonical({"bedrooms": 2}, source_url="https://x", parser_name="t", scrape_ts=None) is None


def test_canonical_listing_model():
    cl = CanonicalListing(
        source_url="https://example.com",
        listed_rent_min=2000,
        parser_name="test@1",
        confidence_score=0.5,
    )
    d = cl.model_dump(mode="json")
    assert d["listed_rent_min"] == 2000
