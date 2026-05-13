"""Load sources (preferred) or buildings.property_url; fetch + parse + persist."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from crawler.fetcher import FetchMode, FetchOptions, fetch_url
from crawler.persist import finish_crawl_run, insert_raw_capture, insert_raw_document, open_crawl_run
from crawler.writer import persist_canonical_listing
from parsers.registry import parse_page

logger = logging.getLogger(__name__)


def run_building_crawl(
    conn,
    *,
    default_fetch_mode: FetchMode | None = None,
    building_limit: int | None = None,
    crawl_run_id: UUID | None = None,
) -> dict[str, Any]:
    """
    For each active source row:
    - fetch HTML (strategy per source or CLI default)
    - persist raw BEFORE parsing (`raw_documents` + legacy `raw_captures`)
    - registry parses (`NextDataParser` before generic HTML)
    - persist canonical listings (append-only snapshots)

    Parser failures are logged per-source and recorded in crawl_run stats.
    """
    run_id = crawl_run_id or open_crawl_run(conn)
    stats: dict[str, Any] = {
        "sources_attempted": 0,
        "raw_documents": 0,
        "listings_written": 0,
        "parser_failures": [],
        "fetch_errors": [],
        "no_parser": [],
        "empty_extract": [],
    }
    err: str | None = None

    try:
        sql = """
            SELECT s.id, s.building_id, s.url, s.crawl_strategy::text,
                   s.wait_selector, b.name
            FROM sources s
            JOIN buildings b ON b.id = s.building_id
            WHERE s.active = true
            ORDER BY b.name, s.url
        """
        args: tuple = ()
        if building_limit is not None:
            sql += " LIMIT %s"
            args = (building_limit,)
        rows = conn.execute(sql, args).fetchall()

        if not rows:
            logger.warning("no_active_sources_fallback_property_url")
            fm_default = (default_fetch_mode.value if default_fetch_mode else "http")
            fb_sql = """
                SELECT NULL::uuid, id AS building_id, property_url AS url,
                       %(fm)s::fetch_mode AS crawl_strategy,
                       NULL::text AS wait_selector, name
                FROM buildings
                ORDER BY name
            """
            rows = conn.execute(fb_sql, {"fm": fm_default}).fetchall()

        scrape_ts = datetime.now(timezone.utc)
        for row in rows:
            sid, bid, url, strat, wait_sel, bname = row
            stats["sources_attempted"] += 1
            building_id = bid if isinstance(bid, UUID) else UUID(str(bid))
            source_id = UUID(str(sid)) if sid else None
            mode = FetchMode(strat) if strat else (default_fetch_mode or FetchMode.HTTP)
            if sid is None and default_fetch_mode is not None:
                mode = default_fetch_mode

            opts = FetchOptions(wait_selector=wait_sel)

            try:
                result = fetch_url(str(url), mode, opts)
            except Exception as exc:  # noqa: BLE001
                stats["fetch_errors"].append({"url": str(url), "error": f"{type(exc).__name__}: {exc}"})
                logger.exception("fetch_failed url=%s", url)
                continue

            try:
                raw_doc_id = insert_raw_document(
                    conn,
                    source_id=source_id,
                    building_id=building_id,
                    crawl_run_id=run_id,
                    result=result,
                )
                stats["raw_documents"] += 1

                insert_raw_capture(conn, building_id=building_id, listing_id=None, result=result)
            except Exception as exc:  # noqa: BLE001
                stats["fetch_errors"].append({"url": str(url), "persist_raw_error": str(exc)})
                logger.exception("persist_raw_failed url=%s", url)
                continue

            meta = {"building_name": bname, "scrape_timestamp": scrape_ts}
            try:
                listings, parser_used, status = parse_page(result.body, result.source_url, meta)
                if status == "no_parser_matched":
                    stats["no_parser"].append({"url": result.source_url})
                elif status == "no_rows_extracted":
                    stats["empty_extract"].append({"url": result.source_url, "parser": parser_used})
                pv = None
                if parser_used and "@" in parser_used:
                    pv = parser_used.split("@", 1)[1]
                for cl in listings:
                    try:
                        persist_canonical_listing(
                            conn,
                            building_id=building_id,
                            raw_document_id=raw_doc_id,
                            canonical=cl,
                            parser_version=pv or None,
                        )
                        stats["listings_written"] += 1
                    except Exception as inner:  # noqa: BLE001
                        stats["parser_failures"].append(
                            {"url": result.source_url, "error": f"{type(inner).__name__}: {inner}"}
                        )
                        logger.exception("persist_canonical_failed url=%s", result.source_url)
            except Exception as exc:  # noqa: BLE001
                stats["parser_failures"].append({"url": str(url), "error": f"{type(exc).__name__}: {exc}"})
                logger.exception("parse_pipeline_failed url=%s", url)

    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    finally:
        finish_crawl_run(conn, run_id, stats, err)

    return stats
