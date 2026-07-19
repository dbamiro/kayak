"""Crawler proxy config: defaults, clear failures, redaction, block-through-proxy."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.config import Settings
from crawler.proxy import (
    ProxyConfig,
    ProxyConfigError,
    get_proxy_config,
    httpx_mounts,
    playwright_proxy_settings,
    redact_proxy_url,
)

SECRET_URL = "http://proxy-user-abc:s3cr3t-p4ss@gate.decodo.com:7000"

FIXTURE_BLOCK = Path(__file__).parent / "fixtures" / "cloudflare_block.html"


def _settings(**overrides) -> Settings:
    # _env_file=None: ignore repo .env so tests are deterministic
    return Settings(_env_file=None, **overrides)


# --- disabled by default -----------------------------------------------------

def test_proxy_disabled_by_default():
    assert _settings().proxy_enabled is False
    assert get_proxy_config(_settings()) is None


def test_disabled_ignores_missing_urls():
    s = _settings(proxy_enabled=False, proxy_http_url="")
    assert get_proxy_config(s) is None


# --- clear failures ----------------------------------------------------------

def test_enabled_without_url_fails_clearly():
    s = _settings(proxy_enabled=True, proxy_provider="decodo")
    with pytest.raises(ProxyConfigError) as exc:
        get_proxy_config(s)
    msg = str(exc.value)
    assert "PROXY_HTTP_URL" in msg
    assert "decodo" in msg


def test_enabled_with_unknown_provider_fails():
    s = _settings(proxy_enabled=True, proxy_provider="sketchy_vendor", proxy_http_url=SECRET_URL)
    with pytest.raises(ProxyConfigError) as exc:
        get_proxy_config(s)
    assert "decodo" in str(exc.value)
    assert "bright_data" in str(exc.value)
    assert "custom" in str(exc.value)


def test_bad_scheme_fails_without_leaking_credentials():
    s = _settings(proxy_enabled=True, proxy_http_url="ftp://user:pass@host:21")
    with pytest.raises(ProxyConfigError) as exc:
        get_proxy_config(s)
    assert "pass" not in str(exc.value)


@pytest.mark.parametrize("provider", ["decodo", "bright_data", "custom"])
def test_supported_providers_accepted(provider):
    s = _settings(proxy_enabled=True, proxy_provider=provider, proxy_http_url=SECRET_URL)
    cfg = get_proxy_config(s)
    assert cfg is not None
    assert cfg.provider == provider


def test_https_url_falls_back_to_http_url():
    s = _settings(proxy_enabled=True, proxy_http_url=SECRET_URL, proxy_https_url="")
    cfg = get_proxy_config(s)
    assert cfg.https_url == SECRET_URL


def test_retry_and_timeout_settings_flow_through():
    s = _settings(
        proxy_enabled=True,
        proxy_http_url=SECRET_URL,
        proxy_max_retries=3,
        proxy_timeout_seconds=9.5,
    )
    cfg = get_proxy_config(s)
    assert cfg.max_retries == 3
    assert cfg.timeout_seconds == 9.5


# --- credentials never printed ----------------------------------------------

def test_redact_proxy_url_strips_credentials():
    redacted = redact_proxy_url(SECRET_URL)
    assert "s3cr3t-p4ss" not in redacted
    assert "proxy-user-abc" not in redacted
    assert "gate.decodo.com" in redacted
    assert redacted.startswith("http://***:***@")


def test_redact_url_without_credentials():
    assert redact_proxy_url("http://plain-host:8080") == "http://plain-host:8080"
    assert redact_proxy_url("") == ""


def test_proxy_config_repr_and_str_redact_credentials():
    cfg = ProxyConfig(
        provider="decodo",
        http_url=SECRET_URL,
        https_url=SECRET_URL,
        max_retries=1,
        timeout_seconds=20.0,
    )
    for rendered in (repr(cfg), str(cfg), f"{cfg}"):
        assert "s3cr3t-p4ss" not in rendered
        assert "proxy-user-abc" not in rendered


def test_fetch_http_logs_never_contain_proxy_url(caplog):
    """fetch_http with proxy on: log output must not include credentials."""
    import httpx

    from crawler import fetcher

    cfg = ProxyConfig(
        provider="decodo",
        http_url=SECRET_URL,
        https_url=SECRET_URL,
        max_retries=0,
        timeout_seconds=5.0,
    )

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.text = "<html><body>ok</body></html>"
    ok_response.headers = {"content-type": "text/html"}
    ok_response.url = "https://public.example-leasing.test/floorplans"

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = ok_response

    with caplog.at_level(logging.DEBUG):
        with patch.object(fetcher, "_resolve_proxy", return_value=cfg), patch.object(
            httpx, "Client", return_value=client
        ) as client_cls:
            result = fetcher.fetch_http("https://public.example-leasing.test/floorplans", use_proxy=True)

    assert result.http_status == 200
    assert client_cls.call_args.kwargs.get("mounts")  # proxy transports mounted
    assert "s3cr3t-p4ss" not in caplog.text
    assert "proxy-user-abc" not in caplog.text
    assert "provider=decodo" in caplog.text


# --- provider adapters ---------------------------------------------------------

def test_httpx_mounts_cover_both_schemes():
    cfg = get_proxy_config(_settings(proxy_enabled=True, proxy_http_url=SECRET_URL))
    mounts = httpx_mounts(cfg)
    assert set(mounts) == {"http://", "https://"}


def test_playwright_proxy_splits_credentials_out_of_server():
    cfg = get_proxy_config(_settings(proxy_enabled=True, proxy_http_url=SECRET_URL))
    pw = playwright_proxy_settings(cfg)
    assert pw["server"] == "http://gate.decodo.com:7000"
    assert pw["username"] == "proxy-user-abc"
    assert pw["password"] == "s3cr3t-p4ss"


# --- proxy off means no proxy --------------------------------------------------

def test_fetch_http_without_proxy_uses_plain_client():
    import httpx

    from crawler import fetcher

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.text = "<html>ok</html>"
    ok_response.headers = {"content-type": "text/html"}
    ok_response.url = "https://public.test/x"

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = ok_response

    with patch.object(httpx, "Client", return_value=client) as client_cls:
        fetcher.fetch_http("https://public.test/x", use_proxy=False)

    assert "mounts" not in client_cls.call_args.kwargs


def test_fetch_url_requesting_proxy_while_misconfigured_fails_clearly():
    from crawler.fetcher import FetchMode, FetchOptions, fetch_url

    bad = _settings(proxy_enabled=True, proxy_http_url="")
    with patch("crawler.proxy.get_settings", return_value=bad):
        with pytest.raises(ProxyConfigError):
            fetch_url("https://public.test/x", FetchMode.HTTP, FetchOptions(use_proxy=True))


# --- block detection still applies through proxy -------------------------------

def test_blocked_page_through_proxy_still_classified_blocked():
    """A Cloudflare challenge fetched via proxy must end status=blocked."""
    from crawler.block_detection import BLOCKED_SOURCE_ERROR
    from crawler.fetcher import FetchMode, FetchResult
    from crawler.run import _process_source_row

    html = FIXTURE_BLOCK.read_text(encoding="utf-8")
    proxied_block = FetchResult(
        source_url="https://www.rentcafe.com/apartments/dc/washington/13-u/default.aspx",
        fetch_mode=FetchMode.HTTP,
        format="html",
        body=html,
        http_status=403,
        content_hash="deadbeef",
    )
    mock_conn = MagicMock()

    with patch("crawler.run.fetch_url", return_value=proxied_block) as mock_fetch, patch(
        "crawler.run.insert_raw_document", return_value=uuid4()
    ), patch("crawler.run.insert_raw_capture"), patch("crawler.run._update_source_health") as health:
        out = _process_source_row(
            mock_conn,
            # 7-element row: use_proxy=True (per-source flag)
            (uuid4(), uuid4(), proxied_block.source_url, "http", None, "Proxy Test Bldg", True),
            run_id=uuid4(),
            default_fetch_mode=None,
            scrape_ts=datetime.now(timezone.utc),
        )

    # Proxy flag was threaded into fetch options
    fetch_opts = mock_fetch.call_args.args[2]
    assert fetch_opts.use_proxy is True

    assert out["status"] == "blocked"
    assert out["snapshots_inserted"] == 0
    assert health.call_args.kwargs["status"] == "blocked"
    assert health.call_args.kwargs["error"] == BLOCKED_SOURCE_ERROR


def test_six_element_source_rows_still_work_without_proxy():
    """Legacy 6-tuple rows default to use_proxy=False."""
    from crawler.fetcher import FetchMode, FetchResult
    from crawler.run import _process_source_row

    result = FetchResult(
        source_url="https://public.test/floorplans",
        fetch_mode=FetchMode.HTTP,
        format="html",
        body="<html><body><p>plain page</p></body></html>",
        http_status=200,
        content_hash="cafe",
    )
    mock_conn = MagicMock()

    with patch("crawler.run.fetch_url", return_value=result) as mock_fetch, patch(
        "crawler.run.insert_raw_document", return_value=uuid4()
    ), patch("crawler.run.insert_raw_capture"), patch("crawler.run._update_source_health"):
        _process_source_row(
            mock_conn,
            (uuid4(), uuid4(), result.source_url, "http", None, "Legacy Row Bldg"),
            run_id=uuid4(),
            default_fetch_mode=None,
            scrape_ts=datetime.now(timezone.utc),
        )

    assert mock_fetch.call_args.args[2].use_proxy is False
