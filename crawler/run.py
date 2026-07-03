"""Load sources (preferred) or buildings.property_url; fetch + parse + persist."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from crawler.block_detection import BLOCKED_SOURCE_ERROR, is_block_page
from crawler.fetcher import FetchMode, FetchOptions, fetch_url
from crawler.persist import finish_crawl_run, insert_raw_capture, insert_raw_document, open_crawl_run
from crawler.writer import persist_canonical_listing
from parsers.registry import parse_page

logger = logging.getLogger(__name__)


def _update_source_health(
    conn,
    *,
    source_id: UUID | None,
    status: str,
    listings_count: int,
    parser_used: str | None,
    error: str | None,
) -> None:
    if not source_id:
        return
    conn.execute(
        """
        UPDATE sources
        SET last_crawl_at = now(),
            last_crawl_status = %(st)s,
            last_listings_count = %(n)s,
            last_parser_used = %(parser)s,
            last_error = %(err)s
        WHERE id = %(sid)s
        """,
        {
            "sid": str(source_id),
            "st": status,
            "n": listings_count,
            "parser": parser_used,
            "err": error,
        },
    )
    conn.commit()


def _process_source_row(
    conn,
    row: tuple,
    *,
    run_id: UUID,
    default_fetch_mode: FetchMode | None,
    scrape_ts: datetime,
) -> dict[str, Any]:
    """Fetch, persist raw, parse, and write listings for one source row."""
    sid, bid, url, strat, wait_sel, bname = row
    building_id = bid if isinstance(bid, UUID) else UUID(str(bid))
    source_id = UUID(str(sid)) if sid else None

    out: dict[str, Any] = {
        "source_id": str(source_id) if source_id else None,
        "building_id": str(building_id),
        "building_name": bname,
        "url": str(url),
        "parser_used": None,
        "listings_extracted": 0,
        "snapshots_inserted": 0,
        "concessions_inserted": 0,
        "fees_inserted": 0,
        "errors": [],
        "status": "success",
        "raw_document_saved": False,
    }

    mode = FetchMode(strat) if strat else (default_fetch_mode or FetchMode.HTTP)
    if sid is None and default_fetch_mode is not None:
        mode = default_fetch_mode

    opts = FetchOptions(wait_selector=wait_sel)

    try:
        result = fetch_url(str(url), mode, opts)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        out["errors"].append({"stage": "fetch", "error": msg})
        out["status"] = "fetch_failed"
        _update_source_health(
            conn,
            source_id=source_id,
            status="failed",
            listings_count=0,
            parser_used=None,
            error=msg[:2000],
        )
        return out

    raw_doc_id: UUID | None = None
    try:
        raw_doc_id = insert_raw_document(
            conn,
            source_id=source_id,
            building_id=building_id,
            crawl_run_id=run_id,
            result=result,
        )
        out["raw_document_saved"] = True
        insert_raw_capture(conn, building_id=building_id, listing_id=None, result=result)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        out["errors"].append({"stage": "persist_raw", "error": msg})
        out["status"] = "persist_raw_failed"
        _update_source_health(conn, source_id=source_id, status="failed", listings_count=0, parser_used=None, error=msg[:2000])
        return out

    if is_block_page(result.body, str(url)):
        out["status"] = "blocked"
        out["errors"].append({"stage": "block_page", "error": BLOCKED_SOURCE_ERROR})
        _update_source_health(
            conn,
            source_id=source_id,
            status="blocked",
            listings_count=0,
            parser_used=None,
            error=BLOCKED_SOURCE_ERROR,
        )
        logger.warning("block_page_detected url=%s source_id=%s", url, source_id)
        return out

    meta = {"building_name": bname, "scrape_timestamp": scrape_ts}
    try:
        listings, parser_used, status = parse_page(result.body, result.source_url, meta)
        out["parser_used"] = parser_used
        out["listings_extracted"] = len(listings)

        if status == "no_parser_matched":
            out["errors"].append({"stage": "parse", "error": "no_parser_matched"})
        elif status == "no_rows_extracted":
            out["errors"].append({"stage": "parse", "error": "no_rows_extracted", "parser": parser_used})

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
                out["snapshots_inserted"] += 1
                if cl.concession_text:
                    out["concessions_inserted"] += 1
                if cl.fee_text:
                    out["fees_inserted"] += 1
            except Exception as inner:  # noqa: BLE001
                out["errors"].append(
                    {"stage": "persist_listing", "error": f"{type(inner).__name__}: {inner}"}
                )
                logger.exception("persist_canonical_failed url=%s", result.source_url)

        if out["snapshots_inserted"] == 0 and out["listings_extracted"] == 0:
            out["status"] = "empty"
        elif out["snapshots_inserted"] < out["listings_extracted"]:
            out["status"] = "partial"
        else:
            out["status"] = "success" if not out["errors"] else "partial"

    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        out["errors"].append({"stage": "parse", "error": msg})
        out["status"] = "parse_failed"
        logger.exception("parse_pipeline_failed url=%s", url)

    err_text = None
    if out["errors"]:
        err_text = str(out["errors"])[:2000]
    _update_source_health(
        conn,
        source_id=source_id,
        status=out["status"],
        listings_count=out["snapshots_inserted"],
        parser_used=out.get("parser_used"),
        error=err_text,
    )
    return out


def run_building_crawl(
    conn,
    *,
    default_fetch_mode: FetchMode | None = None,
    building_limit: int | None = None,
    source_id: UUID | None = None,
    crawl_run_id: UUID | None = None,
) -> dict[str, Any]:
    """
    For each active source row (or one `source_id`, which may be inactive for pilot tests):
    - fetch HTML (strategy per source or CLI default)
    - persist raw BEFORE parsing (`raw_documents` + legacy `raw_captures`)
    - registry parses (`NextDataParser` before generic HTML)
    - persist canonical listings (append-only snapshots)
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
        "source_results": [],
    }
    err: str | None = None

    try:
        if source_id is not None:
            sql = """
                SELECT s.id, s.building_id, s.url, s.crawl_strategy::text,
                       s.wait_selector, b.name
                FROM sources s
                JOIN buildings b ON b.id = s.building_id
                WHERE s.id = %s
            """
            rows = conn.execute(sql, (str(source_id),)).fetchall()
        else:
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
            if source_id is not None:
                stats["fetch_errors"].append({"error": f"source_not_found:{source_id}"})
            else:
                fm_default = default_fetch_mode.value if default_fetch_mode else "http"
                fb_sql = """
                    SELECT NULL::uuid, id AS building_id, property_url AS url,
                           %(fm)s::fetch_mode AS crawl_strategy,
                           NULL::text AS wait_selector, name
                    FROM buildings
                    ORDER BY name
                """
                if building_limit is not None:
                    fb_sql += " LIMIT %s"
                    rows = conn.execute(fb_sql, {"fm": fm_default, "limit": building_limit}).fetchall()
                else:
                    rows = conn.execute(fb_sql, {"fm": fm_default}).fetchall()

        scrape_ts = datetime.now(timezone.utc)
        for row in rows:
            stats["sources_attempted"] += 1
            result = _process_source_row(
                conn,
                row,
                run_id=run_id,
                default_fetch_mode=default_fetch_mode,
                scrape_ts=scrape_ts,
            )
            stats["source_results"].append(result)
            if result.get("status") == "fetch_failed":
                stats["fetch_errors"].append({"url": result["url"], "error": result["errors"]})
            if result.get("listings_extracted", 0) == 0 and result.get("parser_used"):
                stats["empty_extract"].append({"url": result["url"], "parser": result["parser_used"]})
            stats["listings_written"] += result.get("snapshots_inserted", 0)
            if result.get("raw_document_saved"):
                stats["raw_documents"] += 1

            for e in result.get("errors", []):
                if e.get("stage") == "parse" and e.get("error") == "no_parser_matched":
                    stats["no_parser"].append({"url": result["url"]})
                elif e.get("stage") in ("persist_listing", "parse"):
                    stats["parser_failures"].append({"url": result["url"], "error": e})

    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    finally:
        finish_crawl_run(conn, run_id, stats, err)

    return stats
