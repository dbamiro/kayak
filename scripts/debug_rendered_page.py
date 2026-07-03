#!/usr/bin/env python3
"""Save Playwright-rendered HTML and print listing-signal diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from crawler.block_detection import BLOCKED_HINTS, is_block_page
from crawler.page_diagnostics import TERM_CHECKS, analyze_rendered_html, triage_recommendation
from app.config import get_settings


def fetch_rendered_html(url: str, wait_seconds: float) -> str:
    from playwright.sync_api import sync_playwright

    settings = get_settings()
    timeout_ms = int(settings.crawler_timeout_seconds * 1000)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.playwright_headless)
        try:
            context = browser.new_context(user_agent=settings.crawler_user_agent)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(int(wait_seconds * 1000))
            return page.content()
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug rendered HTML from a floorplans URL")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True, help="Path to save HTML, e.g. tmp/debug_html/page.html")
    parser.add_argument("--wait-seconds", type=float, default=8.0, help="Extra wait after domcontentloaded")
    args = parser.parse_args()

    html = fetch_rendered_html(args.url, args.wait_seconds)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    diag = analyze_rendered_html(html, args.url)
    classification = triage_recommendation(diag, listing_count=0)

    print(f"Saved: {out_path} ({diag['byte_count']} bytes)")
    print(f"Title: {diag['title']}")
    blocked = diag["block_page_detected"] or is_block_page(html, args.url)
    print(f"block_page_detected: {blocked}")
    print(f"Triage (0 listings): {classification}")
    if blocked:
        print("\n*** BLOCKED — not valid apartment HTML ***")
        print("Recommendation: mark this source inactive (sources.active = false).")
        print("Do not bypass Cloudflare. Use another public direct property URL or official data access.")
        for hint in BLOCKED_HINTS[:3]:
            print(f"  - {hint}")
        return
    print("\nTerms present:")
    for term in TERM_CHECKS:
        print(f"  {term!r}: {diag['terms_present'].get(term, False)}")
    print(f"\nRent-like pattern count: {diag['rent_like_pattern_count']}")
    print("\nFirst rent-like snippets:")
    for s in diag["rent_like_snippets"]:
        print(f"  - {s}")
    print("\nFirst unit-like snippets:")
    for s in diag["unit_like_snippets"]:
        print(f"  - {s}")
    print("\nFirst floorplan-like snippets:")
    for s in diag["floorplan_like_snippets"]:
        print(f"  - {s}")


if __name__ == "__main__":
    main()
