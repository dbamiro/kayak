"""Generic floorplan / unit card extraction from rendered HTML."""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup, Tag

from models.canonical_listing import CanonicalListing
from parsers.base import BaseParser
from parsers.rentcafe_html_parser import _floorplan_from_url, _parse_float, _parse_money

logger = logging.getLogger(__name__)

RENT_RANGE_RE = re.compile(
    r"(?:Starting\s+at|From)\s*:?\s*\$?\s*([\d,]+(?:\.\d{2})?)"
    r"(?:\s*-\s*\$?\s*([\d,]+(?:\.\d{2})?))?"
    r"|\$\s*([\d,]+(?:\.\d{2})?)\s*-\s*\$\s*([\d,]+(?:\.\d{2})?)"
    r"|\$\s*([\d,]+(?:\.\d{2})?)\s*(?:/|\bmo\b|\bmonth\b)?",
    re.I,
)
BED_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Bed(?:room)?s?)\b|Studio\b", re.I)
BATH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Bath(?:room)?s?)\b", re.I)
SQFT_RE = re.compile(r"(?:Up\s+to\s+)?(\d{3,4})\s*Sq\.?\s*Ft\.?", re.I)
UNIT_RE = re.compile(
    r"(?:Unit|Apt|Apartment)\s*#?\s*(\d{2,5})|#\s*(\d{2,5})\b",
    re.I,
)
AVAILABLE_RE = re.compile(
    r"(Available\s+Now|Available\s+\d{1,2}/\d{1,2}/\d{2,4}|Move[- ]in\s+ready)",
    re.I,
)
CONCESSION_RE = re.compile(
    r"(one month free|move[- ]in special|\d+\s+weeks?\s+free|concession|apply within \d+ hours)",
    re.I,
)
FLOORPLAN_NAME_RE = re.compile(
    r"(?:Floor\s*Plan|Floorplan|Plan)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-]{0,12})",
    re.I,
)

CARD_CLASS_HINTS = re.compile(
    r"card|unit|floorplan|floor-plan|listing|availability|apt-|apartment",
    re.I,
)

# RentCafe-specific pages are handled by rentcafe_html (runs earlier in registry).
RENTCAFE_APARTMENT_HEADER = re.compile(r"Apartment:\s*#\s*\d+", re.I)


def _rents_from_text(text: str) -> tuple[int | None, int | None]:
    rents: list[int] = []
    for m in RENT_RANGE_RE.finditer(text):
        groups = [g for g in m.groups() if g]
        for g in groups:
            val = _parse_money(g)
            if val is not None:
                rents.append(val)
    if not rents:
        return None, None
    return min(rents), max(rents)


def _bedrooms_from_text(text: str) -> float | None:
    if re.search(r"\bStudio\b", text, re.I):
        return 0.0
    m = BED_RE.search(text)
    return _parse_float(m.group(1)) if m else None


def _unit_label(text: str) -> str | None:
    m = UNIT_RE.search(text)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip()


def _floorplan_name(text: str, url: str, page_fp: str | None) -> str | None:
    m = FLOORPLAN_NAME_RE.search(text)
    if m:
        return m.group(1).strip()
    if page_fp:
        return page_fp
    return _floorplan_from_url(url)


def _signal_score(text: str) -> int:
    score = 0
    if RENT_RANGE_RE.search(text):
        score += 1
    if BED_RE.search(text) or re.search(r"\bStudio\b", text, re.I):
        score += 1
    if BATH_RE.search(text):
        score += 1
    if SQFT_RE.search(text):
        score += 1
    if UNIT_RE.search(text):
        score += 1
    if AVAILABLE_RE.search(text) or "available" in text.lower():
        score += 1
    if FLOORPLAN_NAME_RE.search(text) or re.search(r"\bfloor\s*plan\b", text, re.I):
        score += 1
    return score


def _candidate_elements(soup: BeautifulSoup) -> list[tuple[Tag, str]]:
    seen_text: set[str] = set()
    out: list[tuple[Tag, str]] = []
    tags = ("div", "article", "li", "section", "tr", "fieldset")
    for el in soup.find_all(tags):
        classes = " ".join(el.get("class") or [])
        t = el.get_text(" ", strip=True)
        if len(t) < 35 or len(t) > 3000:
            continue
        if t in seen_text:
            continue
        # Prefer card-like containers or blocks with rent
        has_hint = bool(CARD_CLASS_HINTS.search(classes)) or "$" in t
        if not has_hint:
            continue
        if _signal_score(t) < 2:
            continue
        if not RENT_RANGE_RE.search(t):
            continue
        seen_text.add(t)
        out.append((el, t))
    return out


def _page_floorplan_hint(soup: BeautifulSoup, url: str) -> str | None:
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(strip=True)
        if t and len(t) <= 16 and re.match(r"^[A-Za-z0-9\-]+$", t):
            return t.upper()
    return _floorplan_from_url(url)


class FloorplanCardsHtmlParser(BaseParser):
    """Heuristic card/block parser for property sites without __NEXT_DATA__."""

    source_type = "floorplan_cards_html"
    name = "floorplan_cards_html"
    version = "0.1.0"

    def can_parse(self, html: str, url: str) -> bool:
        if not html or len(html) < 400:
            return False
        if RENTCAFE_APARTMENT_HEADER.search(html):
            return False
        text = re.sub(r"<[^>]+>", " ", html)
        if "$" not in text:
            return False
        return _signal_score(text) >= 2

    def parse(self, html: str, url: str, metadata: dict[str, Any]) -> list[CanonicalListing]:
        soup = BeautifulSoup(html, "lxml")
        page_fp = _page_floorplan_hint(soup, url)
        building_hint = metadata.get("building_name")
        page_concession = None
        page_text = soup.get_text("\n", strip=True)
        cm = CONCESSION_RE.search(page_text)
        if cm:
            page_concession = cm.group(0)

        listings: list[CanonicalListing] = []
        seen: set[tuple[str | None, int | None, int | None]] = set()

        for _el, block_text in _candidate_elements(soup):
            rmin, rmax = _rents_from_text(block_text)
            if rmin is None:
                continue
            unit = _unit_label(block_text)
            fp = _floorplan_name(block_text, url, page_fp)
            dedupe_key = (unit or fp, rmin, rmax)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            avail_m = AVAILABLE_RE.search(block_text)
            conf = 0.55 + min(_signal_score(block_text), 5) * 0.06
            if unit:
                conf += 0.08
            conf = min(conf, 0.88)

            listings.append(
                CanonicalListing(
                    building_name=building_hint,
                    floorplan_name=fp,
                    unit_label=unit,
                    bedrooms=_bedrooms_from_text(block_text),
                    bathrooms=_parse_float(BATH_RE.search(block_text).group(1))
                    if BATH_RE.search(block_text)
                    else None,
                    sqft=int(SQFT_RE.search(block_text).group(1)) if SQFT_RE.search(block_text) else None,
                    listed_rent_min=rmin,
                    listed_rent_max=rmax or rmin,
                    available_date=avail_m.group(0) if avail_m else None,
                    concession_text=CONCESSION_RE.search(block_text).group(0) if CONCESSION_RE.search(block_text) else page_concession,
                    source_url=url,
                    parser_name=f"{self.name}@{self.version}",
                    confidence_score=conf,
                    field_confidence={"listed_rent_min": 0.75, "unit_label": 0.7 if unit else 0.0},
                    raw_fragment={"text_excerpt": block_text[:400]},
                )
            )

        if not listings:
            logger.debug("floorplan_cards_html_empty url=%s", url)
        else:
            logger.info("floorplan_cards_html_extracted count=%s url=%s", len(listings), url)
        return listings
