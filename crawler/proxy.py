"""Provider-agnostic crawler proxy configuration (Decodo, Bright Data, custom).

Policy (see docs/CRAWLER_PROXY.md):
- Disabled by default (PROXY_ENABLED=false).
- Public pages only. Never used to bypass Cloudflare, CAPTCHAs, login walls,
  or explicit blocks — blocked/challenge pages are still classified BLOCKED.
- Proxy URLs contain credentials and must never be logged or printed.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.config import Settings, get_settings

SUPPORTED_PROXY_PROVIDERS = ("decodo", "bright_data", "custom")


class ProxyConfigError(RuntimeError):
    """Raised when PROXY_ENABLED=true but the proxy configuration is unusable."""


@dataclass(frozen=True)
class ProxyConfig:
    provider: str
    http_url: str
    https_url: str
    max_retries: int
    timeout_seconds: float

    def __repr__(self) -> str:  # never expose credentials via repr/str
        return (
            f"ProxyConfig(provider={self.provider!r}, "
            f"http_url={redact_proxy_url(self.http_url)!r}, "
            f"https_url={redact_proxy_url(self.https_url)!r}, "
            f"max_retries={self.max_retries}, timeout_seconds={self.timeout_seconds})"
        )

    __str__ = __repr__


def redact_proxy_url(url: str) -> str:
    """Return a log-safe form of a proxy URL: credentials replaced, never echoed."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<redacted>"
    host = parts.hostname or "<redacted>"
    port = f":{parts.port}" if parts.port else ""
    scheme = parts.scheme or "http"
    prefix = "***:***@" if parts.username or parts.password else ""
    return f"{scheme}://{prefix}{host}{port}"


def get_proxy_config(settings: Settings | None = None) -> ProxyConfig | None:
    """Return the active proxy config, or None when PROXY_ENABLED=false.

    Raises ProxyConfigError with a clear message (no credentials) when the
    proxy is enabled but misconfigured.
    """
    s = settings or get_settings()
    if not s.proxy_enabled:
        return None

    provider = (s.proxy_provider or "").strip().lower()
    if provider not in SUPPORTED_PROXY_PROVIDERS:
        raise ProxyConfigError(
            f"PROXY_PROVIDER must be one of {', '.join(SUPPORTED_PROXY_PROVIDERS)} "
            f"(got {provider!r})"
        )

    http_url = (s.proxy_http_url or "").strip()
    https_url = (s.proxy_https_url or "").strip() or http_url
    if not http_url and https_url:
        http_url = https_url
    if not http_url:
        raise ProxyConfigError(
            "PROXY_ENABLED=true but PROXY_HTTP_URL/PROXY_HTTPS_URL are empty. "
            f"Set the {provider} proxy endpoint URL in .env (see docs/CRAWLER_PROXY.md), "
            "or set PROXY_ENABLED=false."
        )

    for label, url in (("PROXY_HTTP_URL", http_url), ("PROXY_HTTPS_URL", https_url)):
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ("http", "https", "socks5"):
            raise ProxyConfigError(
                f"{label} must start with http://, https://, or socks5:// "
                f"(got scheme {scheme or '<none>'!r})"
            )

    return ProxyConfig(
        provider=provider,
        http_url=http_url,
        https_url=https_url,
        max_retries=max(0, int(s.proxy_max_retries)),
        timeout_seconds=float(s.proxy_timeout_seconds),
    )


def httpx_mounts(config: ProxyConfig) -> dict:
    """Per-scheme transport mounts for httpx.Client (httpx >= 0.28)."""
    import httpx

    return {
        "http://": httpx.HTTPTransport(proxy=config.http_url),
        "https://": httpx.HTTPTransport(proxy=config.https_url),
    }


def playwright_proxy_settings(config: ProxyConfig) -> dict:
    """Playwright launch proxy dict; credentials passed as separate fields."""
    parts = urlsplit(config.https_url or config.http_url)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    scheme = parts.scheme or "http"
    out: dict = {"server": f"{scheme}://{host}{port}"}
    if parts.username:
        out["username"] = parts.username
    if parts.password:
        out["password"] = parts.password
    return out
