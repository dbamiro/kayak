"""HTTP + Playwright fetchers with retries, spacing, and optional Playwright waits."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Literal

import httpx
from playwright.sync_api import sync_playwright

from app.config import get_settings
from crawler.proxy import ProxyConfig, get_proxy_config, httpx_mounts, playwright_proxy_settings

logger = logging.getLogger(__name__)

_last_fetch_monotonic = 0.0


class FetchMode(str, Enum):
    HTTP = "http"
    PLAYWRIGHT = "playwright"


CaptureFormat = Literal["html", "json"]


@dataclass
class FetchResult:
    source_url: str
    fetch_mode: FetchMode
    format: CaptureFormat
    body: str
    http_status: int | None
    content_hash: str


@dataclass
class FetchOptions:
    wait_selector: str | None = None
    wait_until: Literal["commit", "domcontentloaded", "load", "domcontentloaded"] = "domcontentloaded"
    screenshot_path: str | None = None
    # Route this fetch through the configured proxy (only if PROXY_ENABLED=true).
    # Public pages only — never to bypass Cloudflare/CAPTCHA/logins/blocks.
    use_proxy: bool = False


def _resolve_proxy(use_proxy: bool) -> ProxyConfig | None:
    """Proxy config for this fetch, or None. Raises ProxyConfigError if the
    proxy is requested and enabled but misconfigured (clear failure, no creds)."""
    if not use_proxy:
        return None
    return get_proxy_config()


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _guess_format(content_type: str | None, body: str) -> CaptureFormat:
    ct = (content_type or "").lower()
    if "json" in ct:
        return "json"
    snippet = body.lstrip()
    if snippet.startswith("{") or snippet.startswith("["):
        return "json"
    return "html"


def _rate_limit_gap() -> None:
    global _last_fetch_monotonic
    settings = get_settings()
    gap_ms = getattr(settings, "crawler_min_interval_ms", 500)
    gap_s = max(0.0, gap_ms / 1000.0)
    now = time.monotonic()
    wait = _last_fetch_monotonic + gap_s - now
    if wait > 0:
        time.sleep(wait)
    _last_fetch_monotonic = time.monotonic()


def fetch_http(url: str, *, use_proxy: bool = False) -> FetchResult:
    settings = get_settings()
    headers = {"User-Agent": settings.crawler_user_agent}
    timeout = settings.crawler_timeout_seconds
    max_retries = getattr(settings, "crawler_max_retries", 2)
    backoff = getattr(settings, "crawler_retry_backoff_seconds", 1.5)

    proxy = _resolve_proxy(use_proxy)
    client_kwargs: dict = {}
    if proxy is not None:
        client_kwargs["mounts"] = httpx_mounts(proxy)
        timeout = proxy.timeout_seconds
        max_retries = proxy.max_retries
        # Log provider only — proxy URLs contain credentials.
        logger.info("fetch_via_proxy provider=%s url=%s", proxy.provider, url)

    _rate_limit_gap()

    last_exc: Exception | None = None
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True, **client_kwargs) as client:
        for attempt in range(max_retries + 1):
            try:
                resp = client.get(url)
                if resp.status_code >= 500 and attempt < max_retries:
                    logger.warning("http_retry url=%s attempt=%s status=%s", url, attempt, resp.status_code)
                    time.sleep(backoff * (attempt + 1))
                    continue
                body = resp.text
                fmt = _guess_format(resp.headers.get("content-type"), body)
                return FetchResult(
                    source_url=str(resp.url),
                    fetch_mode=FetchMode.HTTP,
                    format=fmt,
                    body=body,
                    http_status=resp.status_code,
                    content_hash=_hash_body(body),
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning("http_error url=%s attempt=%s err=%s", url, attempt, exc)
                if attempt >= max_retries:
                    raise
                time.sleep(backoff * (attempt + 1))
        assert last_exc
        raise last_exc


def fetch_playwright(url: str, options: FetchOptions | None = None) -> FetchResult:
    settings = get_settings()
    opts = options or FetchOptions()
    timeout_ms = int(settings.crawler_timeout_seconds * 1000)
    screenshot_on_error = getattr(settings, "playwright_screenshot_on_error", False)

    proxy = _resolve_proxy(opts.use_proxy)
    launch_kwargs: dict = {"headless": settings.playwright_headless}
    if proxy is not None:
        launch_kwargs["proxy"] = playwright_proxy_settings(proxy)
        timeout_ms = int(proxy.timeout_seconds * 1000)
        logger.info("fetch_via_proxy provider=%s url=%s", proxy.provider, url)

    _rate_limit_gap()

    page = None
    body = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(user_agent=settings.crawler_user_agent)
                page = context.new_page()
                page.goto(url, wait_until=opts.wait_until, timeout=timeout_ms)
                if opts.wait_selector:
                    page.wait_for_selector(opts.wait_selector, timeout=min(timeout_ms, 15000))
                body = page.content()
            finally:
                browser.close()
    except Exception:
        if page is not None and (screenshot_on_error or opts.screenshot_path):
            try:
                path = opts.screenshot_path or "/tmp/dmv_playwright_failure.png"
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=path, full_page=True)
                logger.error("playwright_saved_screenshot path=%s url=%s", path, url)
            except Exception as shot_exc:  # noqa: BLE001
                logger.debug("playwright_screenshot_failed %s", shot_exc)
        raise

    fmt = _guess_format(None, body)
    return FetchResult(
        source_url=url,
        fetch_mode=FetchMode.PLAYWRIGHT,
        format=fmt,
        body=body,
        http_status=200,
        content_hash=_hash_body(body),
    )


def fetch_url(url: str, mode: FetchMode, options: FetchOptions | None = None) -> FetchResult:
    if mode == FetchMode.HTTP:
        return fetch_http(url, use_proxy=bool(options and options.use_proxy))
    if mode == FetchMode.PLAYWRIGHT:
        return fetch_playwright(url, options)
    raise ValueError(f"Unsupported fetch mode: {mode}")
