"""RentCafe / Yardi Site Intelligence floorplan pages (DOM text extraction)."""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from models.canonical_listing import CanonicalListing
from parsers.base import BaseParser

logger = logging.getLogger(__name__)

UNIT_HEADER_RE = re.compile(
    r"Apartment:\s*#?\s*(\d+)|(?:Apt|Unit)\.?\s*#?\s*(\d+)|#\s*(\d{2,5})\b",
    re.I,
)
RENT_RE = re.compile(
    r"Starting\s+at:?\s*\$?\s*([\d,]+(?:\.\d{2})?)|\$\s*([\d,]+(?:\.\d{2})?)\s*(?:/|\bper\b)",
    re.I,
)
BED_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Bed(?:room)?s?)\b", re.I)
BATH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Bath(?:room)?s?)\b", re.I)
SQFT_RE = re.compile(r"(?:Up\s+to\s+)?(\d{3,4})\s*Sq\.?\s*Ft\.?", re.I)
CONCESSION_RE = re.compile(
    r"(apply within \d+ hours[^.]{0,120}one month free|one month free[^.]{0,80}|"
    r"special[^.]{0,80}|concession[^.]{0,80})",
    re.I,
)
RENTCAFE_HOST_HINTS = ("rentcafe", "dominionapts", "yardi")


def _parse_money(raw: str | None) -> int | None:
    if not raw:
        return None
    cleaned = raw.replace(",", "").strip()
    try:
        return int(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _floorplan_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[-2].lower() in ("floorplans", "floorplan", "floor-plans"):
        slug = parts[-1]
        if slug and slug.isalnum():
            return slug.upper()
    return None


def _page_text(soup: BeautifulSoup) -> str:
    return soup.get_text("\n", strip=True)


def _extract_page_meta(soup: BeautifulSoup, url: str, page_text: str) -> dict[str, Any]:
    floorplan = _floorplan_from_url(url)
    h1 = soup.find("h1")
    if h1:
        h1_text = h1.get_text(strip=True)
        if h1_text and len(h1_text) <= 12:
            floorplan = floorplan or h1_text.strip().upper()

    bedrooms = None
    bathrooms = None
    sqft = None
    bed_m = BED_RE.search(page_text)
    bath_m = BATH_RE.search(page_text)
    sqft_m = SQFT_RE.search(page_text)
    if bed_m:
        bedrooms = _parse_float(bed_m.group(1))
    if bath_m:
        bathrooms = _parse_float(bath_m.group(1))
    if sqft_m:
        sqft = int(sqft_m.group(1))

    building_name = None
    title = soup.find("title")
    if title and title.string:
        building_name = title.string.split("|")[0].strip() or None
    if not building_name:
        dom_match = re.search(r"\b(Dominion)\b", page_text)
        if dom_match:
            building_name = dom_match.group(1)

    concession_text = None
    for pattern in (
        r"apply within \d+\s+hours[^.]{0,160}one month free[^.]{0,40}",
        r"one month free[^.]{0,120}",
        r"apply within \d+\s+hours[^.]{0,120}",
    ):
        m = re.search(pattern, page_text, re.I)
        if m:
            concession_text = m.group(0).strip()
            break
    if not concession_text:
        con_m = CONCESSION_RE.search(page_text)
        if con_m:
            concession_text = con_m.group(1).strip()

    address = None
    addr_hdr = soup.find(string=re.compile(r"^ADDRESS$", re.I))
    if addr_hdr and isinstance(addr_hdr, str):
        block = addr_hdr.find_parent()
        if block:
            lines = [ln.strip() for ln in block.get_text("\n", strip=True).split("\n") if ln.strip()]
            if len(lines) > 1:
                address = ", ".join(lines[1:3])

    return {
        "building_name": building_name,
        "address": address,
        "floorplan_name": floorplan,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "sqft": sqft,
        "concession_text": concession_text,
    }


def _unit_number_from_header(text: str) -> str | None:
    m = UNIT_HEADER_RE.search(text)
    if not m:
        return None
    for g in m.groups():
        if g:
            return g.strip()
    return None


def _rent_from_text(text: str) -> int | None:
    m = RENT_RE.search(text)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    return _parse_money(raw)


def _card_root(header: Tag) -> Tag | None:
    node: Tag | None = header
    for _ in range(12):
        if node is None:
            break
        class_list = [c.lower() for c in (node.get("class") or [])]
        if "card" in class_list:
            return node
        node = node.parent if isinstance(node.parent, Tag) else None
    return header.parent if isinstance(header.parent, Tag) else header


class RentcafeHtmlParser(BaseParser):
    """Yardi / RentCafe floorplan availability cards (e.g. dominionapts.com)."""

    source_type = "rentcafe_html"
    name = "rentcafe_html"
    version = "0.1.0"

    def can_parse(self, html: str, url: str) -> bool:
        if not html or len(html) < 500:
            return False
        lower = html.lower()
        host = urlparse(url).netloc.lower()
        score = 0
        if any(h in host for h in RENTCAFE_HOST_HINTS):
            score += 1
        if re.search(r"Apartment:\s*#\s*\d+", html, re.I):
            score += 2
        if re.search(r"Starting\s+at", html, re.I):
            score += 1
        if "ysi." in lower or "rentcafe" in lower:
            score += 1
        return score >= 2

    def parse(self, html: str, url: str, metadata: dict[str, Any]) -> list[CanonicalListing]:
        soup = BeautifulSoup(html, "lxml")
        page_text = _page_text(soup)
        meta = _extract_page_meta(soup, url, page_text)
        building_hint = metadata.get("building_name") or meta.get("building_name")
        concession = meta.get("concession_text")

        listings: list[CanonicalListing] = []
        seen_units: set[str] = set()

        headers: list[Tag] = []
        for tag_name in ("h3", "h4", "h5"):
            headers.extend(soup.find_all(tag_name))

        for header in headers:
            header_text = header.get_text(" ", strip=True)
            unit = _unit_number_from_header(header_text)
            if not unit:
                continue
            if unit in seen_units:
                continue

            card = _card_root(header)
            card_text = card.get_text("\n", strip=True) if card else header_text
            rent = _rent_from_text(card_text)
            if rent is None:
                continue

            seen_units.add(unit)
            field_conf: dict[str, float] = {
                "unit_label": 0.9,
                "listed_rent_min": 0.85,
                "floorplan_name": 0.7 if meta.get("floorplan_name") else 0.0,
            }
            confidence = 0.72
            if meta.get("bedrooms") is not None:
                confidence += 0.05
            if meta.get("sqft") is not None:
                confidence += 0.03
            if concession:
                confidence += 0.05
            confidence = min(confidence, 0.92)

            listings.append(
                CanonicalListing(
                    building_name=building_hint,
                    address=meta.get("address"),
                    floorplan_name=meta.get("floorplan_name"),
                    unit_label=unit,
                    bedrooms=meta.get("bedrooms"),
                    bathrooms=meta.get("bathrooms"),
                    sqft=meta.get("sqft"),
                    listed_rent_min=rent,
                    listed_rent_max=rent,
                    concession_text=concession,
                    source_url=url,
                    parser_name=f"{self.name}@{self.version}",
                    confidence_score=confidence,
                    field_confidence=field_conf,
                    raw_fragment={
                        "header": header_text,
                        "card_excerpt": card_text[:500],
                    },
                )
            )

        if not listings:
            logger.debug("rentcafe_html_no_units url=%s", url)
        else:
            logger.info("rentcafe_html_extracted count=%s url=%s", len(listings), url)
        return listings
