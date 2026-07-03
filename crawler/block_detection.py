"""Detect security / bot-block pages (e.g. Cloudflare) — never bypass."""

from __future__ import annotations

import re

BLOCKED_USER_MESSAGE = (
    "This source returned a Cloudflare/security challenge page. "
    "Do not bypass it. Use another public source or direct partner/API access."
)

BLOCKED_SOURCE_ERROR = (
    "blocked: Cloudflare or security challenge page (not valid listing HTML)"
)

BLOCKED_HINTS = [
    "Cloudflare challenge pages (e.g. title \"Just a moment...\") are not apartment data.",
    "Use a direct property floorplans URL or official data access — not an aggregator blocked by Cloudflare.",
    "Set sources.active = false for blocked sources until you have an allowed URL.",
    "Do not add stealth, CAPTCHA solving, Cloudflare bypass, or proxy rotation.",
]

# Case-insensitive substring signals in normalized visible text or raw HTML.
_BLOCK_SIGNALS = (
    "attention required! | cloudflare",
    "sorry, you have been blocked",
    "cf-error-details",
    "you are unable to access",
    "performance & security by cloudflare",
    "checking your browser before accessing",
    "ray id:",
    "access denied",
    "please enable cookies",
    "enable cookies to continue",
    "enable cookies",
    "verify you are human",
    "just a moment...",
    "just a moment",
)

# Strong single-hit phrases (interstitial headlines).
_STRONG_BLOCK_PHRASES = (
    "sorry, you have been blocked",
    "access denied",
    "please enable cookies",
    "enable cookies to continue",
    "verify you are human",
    "complete the captcha",
    "security check to access",
    "just a moment...",
    "just a moment",
)

# Raw HTML markers (scripts/hosts on challenge pages).
_HTML_MARKERS = (
    "challenges.cloudflare.com",
    "cdn-cgi/challenge-platform",
    "__cf_chl_opt",
)


def is_block_page(html: str, url: str) -> bool:
    """
    Return True when HTML looks like a Cloudflare or similar block/challenge interstitial.

    HTTP 200 or 403 with a challenge page is still a block — not a successful crawl.
    """
    _ = url  # reserved for host-specific rules later; no bypass logic by host
    if not html or len(html.strip()) < 80:
        return False

    lower = html.lower()

    for marker in _HTML_MARKERS:
        if marker in lower:
            return True

    if "cf-error-details" in lower:
        return True
    if 'id="cf-wrapper"' in lower or 'class="cf-error' in lower:
        return True

    title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.DOTALL)
    title_lower = ""
    if title_m:
        title_lower = title_m.group(1).strip().lower()
        if "attention required" in title_lower and "cloudflare" in title_lower:
            return True
        if "just a moment" in title_lower:
            return True

    text_lower = re.sub(r"<[^>]+>", " ", lower)
    text_lower = re.sub(r"\s+", " ", text_lower)

    if "challenges.cloudflare.com" in text_lower:
        return True

    hits = sum(1 for sig in _BLOCK_SIGNALS if sig in text_lower)
    if hits >= 2:
        return True

    for phrase in _STRONG_BLOCK_PHRASES:
        if phrase in text_lower:
            return True

    if "you are unable to access" in text_lower and "cloudflare" in text_lower:
        return True

    # Captcha interstitial — ignore reCAPTCHA footer badges on normal leasing pages
    if "protected by recaptcha" in text_lower and "sorry, you have been blocked" not in text_lower:
        pass
    elif "captcha" in text_lower and any(
        x in text_lower
        for x in (
            "sorry, you have been blocked",
            "attention required",
            "verify you are human",
            "security check to access",
            "complete the captcha",
            "just a moment",
            "challenges.cloudflare.com",
        )
    ):
        return True

    return False


def source_status_bucket(last_crawl_status: str | None) -> str:
    """Group sources for admin dashboards: blocked | parser_failure | ok | other."""
    if not last_crawl_status:
        return "never_crawled"
    st = last_crawl_status.lower()
    if st == "blocked":
        return "blocked"
    if st in ("success", "partial"):
        return "ok"
    if st in (
        "failed",
        "fetch_failed",
        "parse_failed",
        "persist_raw_failed",
        "empty",
    ):
        return "parser_failure"
    return "other"
