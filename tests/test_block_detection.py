"""Cloudflare / security block page detection (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from crawler.block_detection import (
    BLOCKED_SOURCE_ERROR,
    BLOCKED_USER_MESSAGE,
    is_block_page,
    source_status_bucket,
)
from crawler.run import _process_source_row

FIXTURE = Path(__file__).parent / "fixtures" / "cloudflare_block.html"
FIXTURE_MOMENT = Path(__file__).parent / "fixtures" / "cloudflare_just_a_moment.html"
BLOCK_URL = "https://www.rentcafe.com/apartments/dc/washington/13-u/default.aspx"
EDISON_URL = "https://www.edisonunionmarket.com/floorplans"


def test_is_block_page_cloudflare_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    assert is_block_page(html, BLOCK_URL) is True


def test_is_block_page_just_a_moment_fixture():
    html = FIXTURE_MOMENT.read_text(encoding="utf-8")
    assert is_block_page(html, EDISON_URL) is True


def test_is_block_page_normal_listing_html_false():
    html = """
    <html><head><title>B1A | Dominion</title></head>
    <body><h3>Apartment: # 617</h3><p>Starting at: $2,200.00</p></body></html>
    """
    assert is_block_page(html, "https://www.dominionapts.com/floorplans/b1a") is False


def test_blocked_user_message_mentions_challenge():
    assert "challenge" in BLOCKED_USER_MESSAGE.lower()
    assert "bypass" in BLOCKED_USER_MESSAGE.lower()


def test_source_status_bucket_blocked():
    assert source_status_bucket("blocked") == "blocked"
    assert source_status_bucket("empty") == "parser_failure"
    assert source_status_bucket("success") == "ok"


def _block_fetch_result(html: str, url: str = BLOCK_URL) -> "FetchResult":
    from crawler.fetcher import FetchMode, FetchResult

    return FetchResult(
        source_url=url,
        fetch_mode=FetchMode.PLAYWRIGHT,
        format="html",
        body=html,
        http_status=403,
        content_hash="abc123",
    )


def test_test_parse_summary_blocked_from_fixture():
    from crawler.test_parse import main
    import sys

    html = FIXTURE.read_text(encoding="utf-8")
    mock_result = _block_fetch_result(html)

    with patch("crawler.test_parse.fetch_url", return_value=mock_result):
        with patch.object(sys, "argv", ["test_parse", "--url", BLOCK_URL, "--strategy", "playwright"]):
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                main()
            out = json.loads(buf.getvalue())

    assert out["summary"]["parse_status"] == "blocked"
    assert out["summary"]["listing_count"] == 0
    assert out.get("blocked") is True
    assert out.get("message") == BLOCKED_USER_MESSAGE
    assert out["hints"]["block_page"] is True


def test_test_parse_summary_blocked_just_a_moment():
    from crawler.test_parse import main
    import sys

    html = FIXTURE_MOMENT.read_text(encoding="utf-8")
    mock_result = _block_fetch_result(html, EDISON_URL)

    with patch("crawler.test_parse.fetch_url", return_value=mock_result):
        with patch.object(
            sys,
            "argv",
            ["test_parse", "--url", EDISON_URL, "--strategy", "playwright", "--parser", "auto"],
        ):
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                main()
            out = json.loads(buf.getvalue())

    assert out["summary"]["parse_status"] == "blocked"
    assert out["summary"]["listing_count"] == 0
    assert out["diagnostics"]["block_page_detected"] is True


@pytest.mark.db
def test_daily_run_blocked_skips_snapshots():
    """Integration: _process_source_row must not insert snapshots on block HTML."""
    pytest.importorskip("psycopg")
    from app.db import close_pool, get_pool

    html = FIXTURE.read_text(encoding="utf-8")
    mock_result = _block_fetch_result(html)

    pool = get_pool()
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT id FROM sources WHERE url ILIKE '%rentcafe.com/kayak-test-alpha%' LIMIT 1"
            ).fetchone()
            assert row is not None, "test seed must include rentcafe source"
            sid = row[0]
            bid_row = conn.execute(
                "SELECT building_id, url, crawl_strategy::text, wait_selector, b.name "
                "FROM sources s JOIN buildings b ON b.id = s.building_id WHERE s.id = %s",
                (str(sid),),
            ).fetchone()
            before = conn.execute(
                "SELECT COUNT(*) FROM listing_snapshots ls "
                "JOIN listings l ON l.id = ls.listing_id WHERE l.building_id = %s",
                (str(bid_row[0]),),
            ).fetchone()[0]

            from datetime import datetime, timezone

            from crawler.run import open_crawl_run

            run_id = open_crawl_run(conn)
            with patch("crawler.run.fetch_url", return_value=mock_result):
                out = _process_source_row(
                    conn,
                    (sid, bid_row[0], bid_row[1], bid_row[2], bid_row[3], bid_row[4]),
                    run_id=run_id,
                    default_fetch_mode=None,
                    scrape_ts=datetime.now(timezone.utc),
                )

            after = conn.execute(
                "SELECT COUNT(*) FROM listing_snapshots ls "
                "JOIN listings l ON l.id = ls.listing_id WHERE l.building_id = %s",
                (str(bid_row[0]),),
            ).fetchone()[0]

            health = conn.execute(
                "SELECT last_crawl_status, last_listings_count, last_error FROM sources WHERE id = %s",
                (str(sid),),
            ).fetchone()
    finally:
        close_pool()

    assert out["status"] == "blocked"
    assert out["snapshots_inserted"] == 0
    assert after == before
    assert health[0] == "blocked"
    assert health[1] == 0
    assert BLOCKED_SOURCE_ERROR in (health[2] or "")


def test_process_source_row_blocked_unit():
    """Unit test without DB: mock conn and fetch."""
    from datetime import datetime, timezone

    html = FIXTURE_MOMENT.read_text(encoding="utf-8")
    mock_result = _block_fetch_result(html, EDISON_URL)
    building_id = uuid4()
    source_id = uuid4()
    mock_conn = MagicMock()

    with patch("crawler.run.fetch_url", return_value=mock_result), patch(
        "crawler.run.insert_raw_document", return_value=uuid4()
    ), patch("crawler.run.insert_raw_capture"), patch("crawler.run._update_source_health") as mock_health:
        out = _process_source_row(
            mock_conn,
            (source_id, building_id, EDISON_URL, "playwright", None, "Test Building"),
            run_id=uuid4(),
            default_fetch_mode=None,
            scrape_ts=datetime.now(timezone.utc),
        )

    assert out["status"] == "blocked"
    assert out["snapshots_inserted"] == 0
    assert out["listings_extracted"] == 0
    mock_health.assert_called_once()
    call_kw = mock_health.call_args.kwargs
    assert call_kw["status"] == "blocked"
    assert call_kw["listings_count"] == 0
    assert call_kw["error"] == BLOCKED_SOURCE_ERROR
