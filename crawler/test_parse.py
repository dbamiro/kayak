"""CLI: fetch a URL and print CanonicalListing JSON (optional DB write)."""

from __future__ import annotations

import argparse
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
from crawler.fetcher import FetchMode, FetchOptions, fetch_url
from crawler.persist import insert_raw_document
from crawler.writer import persist_canonical_listing
from models.canonical_listing import CanonicalListing
from parsers.registry import get_parser_by_name, parse_page

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test fetch + Next.js/__NEXT_DATA__ parsing without DB writes")
    parser.add_argument("--url", required=True)
    parser.add_argument("--strategy", choices=["http", "playwright"], default="http")
    parser.add_argument("--parser", default=None, help="Force parser name: next_data | generic_html | registry")
    parser.add_argument("--wait-selector", default=None)
    parser.add_argument("--write", action="store_true", help="Persist raw_documents + snapshots (needs DATABASE_URL)")
    parser.add_argument("--building-id", default=None, help="UUID when using --write")
    parser.add_argument("--source-id", default=None, help="Optional UUID for raw_documents.source_id")
    args = parser.parse_args()

    mode = FetchMode(args.strategy)
    opts = FetchOptions(wait_selector=args.wait_selector)

    result = fetch_url(args.url, mode, opts)
    logger.info("fetched bytes=%s hash=%s", len(result.body), result.content_hash[:12])

    scrape_ts = datetime.now(timezone.utc)
    meta = {"building_name": None, "scrape_timestamp": scrape_ts}

    listings: list[CanonicalListing]
    used = args.parser

    if args.parser and args.parser != "registry":
        plug = get_parser_by_name(args.parser)
        listings = plug.parse(result.body, result.source_url, meta)
        used = plug.name
        status = None
    else:
        listings, pname, status = parse_page(result.body, result.source_url, meta)
        used = pname or status or "registry"

    adapter = TypeAdapter(list[CanonicalListing])
    print(adapter.dump_json(listings, exclude_none=False).decode("utf-8"))

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
            for cl in listings:
                persist_canonical_listing(
                    conn,
                    building_id=bid,
                    raw_document_id=rid,
                    canonical=cl,
                    parser_version=used or "",
                )
        close_pool()


if __name__ == "__main__":
    main()
