"""Pytest configuration: isolated test DB + deterministic seed for @pytest.mark.db tests."""

from __future__ import annotations

import os

import pytest

from tests.db_bootstrap import bootstrap_test_database, get_test_database_url, postgres_reachable, reset_test_data

# Pytest always targets the isolated test database — never dev/prod data.
_TEST_URL = get_test_database_url()
os.environ["DATABASE_URL"] = _TEST_URL
os.environ.setdefault("TEST_DATABASE_URL", _TEST_URL)
os.environ.setdefault("JWT_SECRET", "pytest-local-jwt-secret-not-for-production-use")
os.environ.setdefault("MOCK_AUTH_MODE", "true")
os.environ.setdefault("MOCK_CHECKOUT_MODE", "true")
os.environ.setdefault("SHOW_DEMO_DATA", "true")

_SESSION_READY = False


def _close_app_pool() -> None:
    from app.db import close_pool

    close_pool()


def _clear_settings_cache() -> None:
    from app.config import get_settings

    get_settings.cache_clear()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "db: integration test requiring Postgres at TEST_DATABASE_URL (default kayak_test)",
    )


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    from app.rate_limit import reset_rate_limits_for_tests

    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


@pytest.fixture(autouse=True)
def _db_test_lifecycle(request: pytest.FixtureRequest) -> None:
    """Bootstrap kayak_test once; reset deterministic seed before each db test."""
    if request.node.get_closest_marker("db") is None:
        yield
        return

    url = get_test_database_url()
    global _SESSION_READY
    if not _SESSION_READY:
        if not postgres_reachable(url):
            pytest.skip(
                f"Postgres not reachable at {url}. "
                "Start with: docker compose up -d postgres && ./scripts/bootstrap_test_db.sh"
            )
        bootstrap_test_database(url)
        _SESSION_READY = True
        os.environ["DATABASE_URL"] = url
        _clear_settings_cache()
        _close_app_pool()

    reset_test_data(url)
    _clear_settings_cache()
    _close_app_pool()
    yield
    _close_app_pool()


@pytest.fixture
def conn(request: pytest.FixtureRequest):
    """Direct Postgres connection for integration tests that bypass the HTTP API."""
    if request.node.get_closest_marker("db") is None:
        pytest.skip("conn fixture requires @pytest.mark.db")
    from app.db import get_pool

    with get_pool().connection() as connection:
        yield connection
