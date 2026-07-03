"""CLI: fetch a URL and print CanonicalListing JSON (optional DB write)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

ROOT = None
if __package__ is None or __package__ == "":
    import os

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from pydantic import TypeAdapter

from app.db import close_pool, get_pool
from crawler.block_detection import BLOCKED_HINTS, BLOCKED_USER_MESSAGE, is_block_page
from crawler.fetcher import FetchMode, FetchOptions, fetch_url
from crawler.page_diagnostics import analyze_rendered_html, triage_recommendation
from crawler.persist import insert_raw_document
from crawler.writer import persist_canonical_listing
from models.canonical_listing import CanonicalListing
from parsers.registry import get_parser_by_name, parse_page

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ZERO_LISTINGS_HELP = [
    "Confirm the URL is the availability/floorplans page (not marketing-only).",
    "Retry with --strategy playwright if the list is rendered client-side.",
    "View page source for <script id=\"__NEXT_DATA__\"> — if present, use --parser next_data.",
    "If __NEXT_DATA__ is missing, rent may load via XHR/API → site-specific parser needed.",
    "Add --wait-selector \"css.selector\" so Playwright waits for the price table.",
    "Inspect saved HTML in raw_documents after a crawl, or save the page locally.",
    "See docs/ADDING_REAL_PROPERTY_SOURCES.md",
]

ZERO_LISTINGS_TRIAGE = [
    "python scripts/debug_rendered_page.py --url \"<url>\" --out tmp/debug_html/site.html",
    "python scripts/debug_xhr.py --url \"<url>\"",
    "If XHR JSON endpoint found → build NEEDS_XHR_PARSER site handler (do not bypass auth).",
    "If HTML has rent/unit text but 0 listings → tune floorplan_cards_html or add site parser.",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Test fetch + parse; prints JSON summary + listings (no DB by default)")
    parser.add_argument("--url", required=True)
    parser.add_argument("--strategy", choices=["http", "playwright"], default="http")
    parser.add_argument(
        "--parser",
        default="auto",
        help="auto (registry) | next_data | rentcafe_html | floorplan_cards_html | generic_html",
    )
    parser.add_argument("--wait-selector", default=None)
    parser.add_argument("--write", action="store_true", help="Persist raw_documents + snapshots (needs DATABASE_URL)")
    parser.add_argument("--building-id", default=None, help="UUID when using --write")
    parser.add_argument("--source-id", default=None, help="Optional UUID for raw_documents.source_id")
    args = parser.parse_args()

    mode = FetchMode(args.strategy)
    opts = FetchOptions(wait_selector=args.wait_selector)

    result = fetch_url(args.url, mode, opts)
    logger.info("fetched bytes=%s hash=%s status=%s", len(result.body), result.content_hash[:12], result.http_status)

    scrape_ts = datetime.now(timezone.utc)
    meta = {"building_name": None, "scrape_timestamp": scrape_ts}
    diag = analyze_rendered_html(result.body, args.url)

    listings: list[CanonicalListing] = []
    used = args.parser
    parse_status: str | None = None
    blocked = is_block_page(result.body, args.url)

    if blocked:
        parse_status = "blocked"
        used = None
    elif args.parser in (None, "auto", "registry"):
        listings, pname, parse_status = parse_page(result.body, result.source_url, meta)
        used = pname or parse_status or "auto"
    else:
        plug = get_parser_by_name(args.parser)
        listings = plug.parse(result.body, result.source_url, meta)
        used = plug.name

    confidences = [cl.confidence_score for cl in listings]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    max_conf = max(confidences) if confidences else 0.0

    adapter = TypeAdapter(list[CanonicalListing])
    classification = triage_recommendation(diag, len(listings))

    payload: dict = {
        "summary": {
            "url": args.url,
            "strategy": args.strategy,
            "parser": used,
            "parse_status": "blocked" if blocked else parse_status,
            "listing_count": len(listings),
            "avg_confidence": round(avg_conf, 4),
            "max_confidence": round(max_conf, 4),
            "http_status": result.http_status,
            "content_hash": result.content_hash,
            "wrote_to_db": False,
            "triage_classification": classification,
        },
        "diagnostics": {
            "block_page_detected": diag["block_page_detected"],
            "rendered_html_has_rent_amounts": diag["rendered_html_has_rent_amounts"],
            "rendered_html_has_floorplan_terms": diag["rendered_html_has_floorplan_terms"],
            "rendered_html_has_unit_terms": diag["rendered_html_has_unit_terms"],
            "rent_like_pattern_count": diag["rent_like_pattern_count"],
        },
        "listings": json.loads(adapter.dump_json(listings, exclude_none=False).decode("utf-8")),
    }
    if blocked:
        payload["blocked"] = True
        payload["message"] = BLOCKED_USER_MESSAGE
        payload["hints"] = {
            "block_page": True,
            "suggestions": BLOCKED_HINTS,
            "deactivate_source": "UPDATE sources SET active = false WHERE url = '<this-url>';",
        }
    elif len(listings) == 0:
        payload["zero_listings_help"] = ZERO_LISTINGS_HELP
        payload["hints"] = {
            "next_data_script_present": "__NEXT_DATA__" in result.body,
            "recommendation": ZERO_LISTINGS_TRIAGE,
            "triage_classification": classification,
        }
        payload["diagnostics"]["recommendation"] = classification

    print(json.dumps(payload, indent=2, default=str))

    if args.write and blocked:
        raise SystemExit("Refusing --write: fetch returned a security block page (not valid listing data).")

    if args.write:
        if not args.building_id:
            raise SystemExit("--write requires --building-id")

        pool = get_pool()
        with pool.connection() as conn:
            sid = args.source_id
            bid = UUID(args.building_id)
            rid = insert_raw_document(
                conn,
                source_id=UUID(sid) if sid else None,
                building_id=bid,
                crawl_run_id=None,
                result=result,
            )
            written = 0
            for cl in listings:
                persist_canonical_listing(
                    conn,
                    building_id=bid,
                    raw_document_id=rid,
                    canonical=cl,
                    parser_version=used or "",
                )
                written += 1
        close_pool()
        logger.info("wrote %s listings to database (building_id=%s)", written, args.building_id)


if __name__ == "__main__":
    main()
