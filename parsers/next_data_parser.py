"""Extract listings from Next.js `__NEXT_DATA__` embedded JSON."""

from __future__ import annotations

import json
import logging
from typing import Any

from bs4 import BeautifulSoup

from models.canonical_listing import CanonicalListing
from parsers.base import BaseParser
from parsers.listing_extract import (
    candidate_to_canonical,
    deep_find_candidate_objects,
)

logger = logging.getLogger(__name__)


def extract_next_data_json(html: str) -> dict[str, Any] | None:
    """Parse `<script id=\"__NEXT_DATA__\" type=\"application/json\">`."""
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    raw = tag.string.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("next_data_json_decode_failed: %s", exc)
        return None


class NextDataParser(BaseParser):
    """Generic recursive extractor — does not rely on a single JSON path."""

    source_type = "next_js_embedded"
    name = "next_data"
    version = "0.2.0"

    def can_parse(self, html: str, url: str) -> bool:
        _ = url
        if extract_next_data_json(html) is not None:
            return True
        return "__NEXT_DATA__" in html

    def parse(self, html: str, url: str, metadata: dict[str, Any]) -> list[CanonicalListing]:
        building_name_hint = metadata.get("building_name")
        payload = extract_next_data_json(html)
        if not payload:
            return []

        candidates = deep_find_candidate_objects(payload, min_score=3)
        out: list[CanonicalListing] = []
        seen: set[tuple[Any, ...]] = set()

        for obj in candidates:
            try:
                cl = candidate_to_canonical(
                    obj,
                    source_url=url,
                    parser_name=f"{self.name}@{self.version}",
                    scrape_ts=metadata.get("scrape_timestamp"),
                    building_name_hint=building_name_hint,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("next_data_candidate_skip: %s", exc)
                continue
            if not cl:
                continue
            dedupe_key = (
                cl.floorplan_name,
                cl.unit_label,
                cl.listed_rent_min,
                cl.listed_rent_max,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            out.append(cl)

        if not out:
            logger.info("next_data_no_listings url=%s candidates=%s", url, len(candidates))
        return out
