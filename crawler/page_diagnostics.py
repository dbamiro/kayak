"""Rendered HTML diagnostics for floorplan triage (no network)."""

from __future__ import annotations

import re
from typing import Any

from crawler.block_detection import is_block_page

TERM_CHECKS: tuple[str, ...] = (
    "$",
    "Available",
    "Availability",
    "Floorplan",
    "Floor Plan",
    "Unit",
    "Apartment",
    "Bedroom",
    "Bathroom",
    "Sq. Ft.",
    "Rent",
    "Apply",
)

RENT_LIKE_RE = re.compile(
    r"(?:Starting\s+at|From)\s*:?\s*\$[\d,]+(?:\.\d{2})?"
    r"|\$[\d,]+(?:\.\d{2})?\s*(?:/|\bmo\b|\bmonth\b)"
    r"|\$[\d,]+(?:\.\d{2})?\s*-\s*\$[\d,]+(?:\.\d{2})?",
    re.I,
)
UNIT_LIKE_RE = re.compile(
    r"(?:Unit|Apt|Apartment)\s*#?\s*\d{2,5}"
    r"|#\s*\d{2,5}\b",
    re.I,
)
FLOORPLAN_LIKE_RE = re.compile(
    r"(?:Floor\s*Plan|Floorplan)\s*[:\-]?\s*[A-Z0-9]{1,8}\b"
    r"|\b[A-Z]{1,2}\d{1,2}[A-Z]?\b",
    re.I,
)


def _visible_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return re.sub(r"\n{2,}", "\n", text)


def _unique_snippets(pattern: re.Pattern[str], text: str, limit: int = 20) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in pattern.finditer(text):
        s = m.group(0).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= limit:
            break
    return out


def analyze_rendered_html(html: str, url: str) -> dict[str, Any]:
    """Diagnostics for triage: block detection, term presence, rent/unit snippets."""
    text = _visible_text(html)
    text_lower = text.lower()
    title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.DOTALL)
    title = title_m.group(1).strip() if title_m else ""

    terms_present: dict[str, bool] = {}
    for term in TERM_CHECKS:
        if term == "$":
            terms_present[term] = "$" in text
        else:
            terms_present[term] = term.lower() in text_lower

    rent_snippets = _unique_snippets(RENT_LIKE_RE, text)
    unit_snippets = _unique_snippets(UNIT_LIKE_RE, text)
    floorplan_snippets = _unique_snippets(FLOORPLAN_LIKE_RE, text)

    return {
        "byte_count": len(html.encode("utf-8")),
        "title": title,
        "block_page_detected": is_block_page(html, url),
        "terms_present": terms_present,
        "rent_like_pattern_count": len(rent_snippets),
        "rent_like_snippets": rent_snippets,
        "unit_like_snippets": unit_snippets,
        "floorplan_like_snippets": floorplan_snippets,
        "rendered_html_has_rent_amounts": bool(rent_snippets),
        "rendered_html_has_floorplan_terms": terms_present.get("Floorplan", False)
        or terms_present.get("Floor Plan", False)
        or bool(floorplan_snippets),
        "rendered_html_has_unit_terms": terms_present.get("Unit", False)
        or terms_present.get("Apartment", False)
        or bool(unit_snippets),
    }


def triage_recommendation(diag: dict[str, Any], listing_count: int) -> str:
    if diag.get("block_page_detected"):
        return "BLOCKED"
    if listing_count > 0:
        return "PASS"
    if diag.get("rendered_html_has_rent_amounts") or diag.get("rendered_html_has_unit_terms"):
        return "NEEDS_HTML_PARSER"
    if diag.get("rendered_html_has_floorplan_terms"):
        return "NEEDS_HTML_PARSER"
    if not any(diag.get("terms_present", {}).values()):
        return "NOT_VIABLE"
    return "NEEDS_XHR_PARSER"
