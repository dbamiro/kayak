"""HTML fallback parser (placeholder DOM selectors)."""

from __future__ import annotations

import logging
from typing import Any

from models.canonical_listing import CanonicalListing
from parsers.base import BaseParser

logger = logging.getLogger(__name__)


class GenericHtmlApartmentParser(BaseParser):
    """
    Last-resort parser: extend with site-specific CSS selectors.

    `can_parse` is permissive so it runs after specialized parsers that returned no rows.
    """

    source_type = "generic_html"
    name = "generic_html"
    version = "0.1.0"

    def can_parse(self, html: str, url: str) -> bool:
        _ = url
        return bool(html and len(html) > 200)

    def parse(self, html: str, url: str, metadata: dict[str, Any]) -> list[CanonicalListing]:
        _ = (html, url, metadata)
        # PLACEHOLDER: add BeautifulSoup selectors per property stack (Entrata/RealPage/etc.).
        logger.debug("generic_html_noop url=%s", url)
        return []
