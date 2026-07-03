"""Ordered parser chain — first successful extraction wins."""

from __future__ import annotations

import logging
from typing import Any

from models.canonical_listing import CanonicalListing
from parsers.base import BaseParser
from parsers.floorplan_cards_html_parser import FloorplanCardsHtmlParser
from parsers.generic_html import GenericHtmlApartmentParser
from parsers.next_data_parser import NextDataParser
from parsers.rentcafe_html_parser import RentcafeHtmlParser

logger = logging.getLogger(__name__)

PARSER_REGISTRY: list[BaseParser] = [
    NextDataParser(),
    RentcafeHtmlParser(),
    FloorplanCardsHtmlParser(),
    GenericHtmlApartmentParser(),
]


def parse_page(
    html: str,
    url: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[list[CanonicalListing], str | None, str | None]:
    """
    Walk `PARSER_REGISTRY` in order.

    Returns (listings, parser_name_used, status_reason).
    """
    meta = dict(metadata or {})
    matched_any = False
    for parser in PARSER_REGISTRY:
        try:
            if not parser.can_parse(html, url):
                continue
            matched_any = True
            listings = parser.parse(html, url, meta)
            if listings:
                logger.info("parser_selected name=%s listings=%s url=%s", parser.name, len(listings), url)
                return listings, parser.name, None
            logger.debug("parser_empty name=%s url=%s", parser.name, url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("parser_failed name=%s url=%s err=%s", parser.name, url, exc)
            continue

    if not matched_any:
        logger.warning("no_parser_matched url=%s", url)
        return [], None, "no_parser_matched"
    logger.warning("parser_matched_but_extracted_nothing url=%s", url)
    return [], None, "no_rows_extracted"


def get_parser_by_name(name: str) -> BaseParser:
    """Resolve a parser for CLI experiments (`next_data`, `generic_html`)."""
    mapping = {p.name: p for p in PARSER_REGISTRY}
    if name not in mapping:
        raise KeyError(f"Unknown parser: {name}")
    # Return fresh instance for thread safety if parsers gain state later
    if name == "next_data":
        return NextDataParser()
    if name == "generic_html":
        return GenericHtmlApartmentParser()
    if name == "rentcafe_html":
        return RentcafeHtmlParser()
    if name == "floorplan_cards_html":
        return FloorplanCardsHtmlParser()
    return mapping[name]
