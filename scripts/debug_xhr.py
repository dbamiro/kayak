#!/usr/bin/env python3
"""Discover XHR/API responses while a floorplans page loads (no bypass)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.config import get_settings
from crawler.block_detection import BLOCKED_HINTS, is_block_page

URL_KEYWORDS = (
    "floor",
    "floorplan",
    "availability",
    "available",
    "unit",
    "units",
    "apartment",
    "pricing",
    "rent",
    "search",
    "inventory",
    "property",
)

MAX_JSON_PREVIEW = 1000
MAX_TEXT_PREVIEW = 500


def url_is_relevant(url: str) -> bool:
    lower = url.lower()
    return any(k in lower for k in URL_KEYWORDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Log network responses during Playwright page load")
    parser.add_argument("--url", required=True)
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    settings = get_settings()
    timeout_ms = int(settings.crawler_timeout_seconds * 1000)
    hits: list[dict] = []

    def on_response(response) -> None:
        try:
            url = response.url
            if not url_is_relevant(url):
                return
            req = response.request
            method = req.method if req else "?"
            status = response.status
            ctype = (response.headers.get("content-type") or "").split(";")[0].strip()
            entry: dict = {
                "method": method,
                "status": status,
                "content_type": ctype,
                "url": url,
            }
            body_preview = ""
            try:
                if "json" in ctype.lower():
                    raw = response.body()
                    if len(raw) <= 500_000:
                        text = raw.decode("utf-8", errors="replace")
                        body_preview = text[:MAX_JSON_PREVIEW]
                        entry["preview_kind"] = "json"
                elif "html" in ctype.lower() or "text" in ctype.lower():
                    raw = response.body()
                    if len(raw) <= 200_000:
                        text = raw.decode("utf-8", errors="replace")
                        body_preview = text[:MAX_TEXT_PREVIEW]
                        entry["preview_kind"] = "text"
            except Exception as exc:  # noqa: BLE001
                body_preview = f"<body read error: {exc}>"
            if body_preview:
                entry["preview"] = body_preview
            hits.append(entry)
        except Exception:
            pass

    print(f"Loading {args.url} (listening for XHR/API URLs matching keywords)...")
    page_html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.playwright_headless)
        try:
            context = browser.new_context(user_agent=settings.crawler_user_agent)
            page = context.new_page()
            page.on("response", on_response)
            page.goto(args.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(int(args.wait_seconds * 1000))
            page_html = page.content()
        finally:
            browser.close()

    if is_block_page(page_html, args.url):
        print("block_page_detected: true")
        print("Recommendation: mark source inactive (sources.active = false). Do not bypass Cloudflare.")
        for hint in BLOCKED_HINTS[:3]:
            print(f"  - {hint}")
        return

    print("block_page_detected: false")

    if not hits:
        print("No relevant network responses captured. Data may be embedded in HTML or use different URL patterns.")
        return

    print(f"\nFound {len(hits)} relevant response(s):\n")
    for i, h in enumerate(hits, 1):
        print(f"--- [{i}] {h['method']} {h['status']} {h['content_type']} ---")
        print(h["url"])
        if h.get("preview"):
            print("Preview:")
            print(h["preview"])
            if h.get("preview_kind") == "json":
                try:
                    parsed = json.loads(h["preview"] + ("..." if len(h["preview"]) >= MAX_JSON_PREVIEW else ""))
                    if isinstance(parsed, (dict, list)):
                        print(f"(valid JSON fragment, keys/types: {type(parsed).__name__})")
                except json.JSONDecodeError:
                    pass
        print()


if __name__ == "__main__":
    main()
