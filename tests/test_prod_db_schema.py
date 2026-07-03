"""Production database bootstrap and schema verification tests."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from app.db_schema import (
    DEMO_SEED_FILES,
    PRODUCTION_SAFE_SEED_FILES,
    REQUIRED_PLAN_CODES,
    REQUIRED_TABLES,
    assert_seed_file_allowed,
    demo_incentive_count,
    missing_plan_codes,
    missing_tables,
)
from tests.db_bootstrap import (
    admin_database_url,
    bootstrap_production_schema,
    bootstrap_schema,
    get_test_database_url,
    postgres_reachable,
    verify_schema,
)

pytestmark = pytest.mark.skipif(
    not postgres_reachable(get_test_database_url()),
    reason="Postgres not reachable for kayak_test",
)


def test_required_tables_constant_covers_incentive_layer() -> None:
    assert "incentives" in REQUIRED_TABLES
    assert "incentive_snapshots" in REQUIRED_TABLES
    assert "incentive_sources" in REQUIRED_TABLES
    assert "customer_entitlements" in REQUIRED_TABLES
    assert "stripe_webhook_events" in REQUIRED_TABLES


def test_demo_seeds_blocked_in_production() -> None:
    for name in DEMO_SEED_FILES:
        with pytest.raises(ValueError, match="Demo seed"):
            assert_seed_file_allowed(name, production=True)


def test_production_safe_seed_allowed() -> None:
    for name in PRODUCTION_SAFE_SEED_FILES:
        assert_seed_file_allowed(name, production=True)


def test_production_bootstrap_has_all_tables_and_plans() -> None:
    base_url = get_test_database_url()
    db_name = f"kayak_prod_verify_{uuid.uuid4().hex[:8]}"
    test_url = base_url.rsplit("/", 1)[0] + f"/{db_name}"

    admin_url = admin_database_url(test_url)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{db_name}"')

    try:
        bootstrap_production_schema(test_url)
        errors = verify_schema(test_url)
        assert errors == []

        with psycopg.connect(test_url) as conn:
            assert missing_tables(conn) == []
            assert missing_plan_codes(conn) == []
            assert demo_incentive_count(conn) == 0
            for code in REQUIRED_PLAN_CODES:
                row = conn.execute(
                    "SELECT 1 FROM plans WHERE code = %s AND is_active = true",
                    (code,),
                ).fetchone()
                assert row is not None, f"missing active plan {code}"
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (db_name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')


def test_dev_schema_bootstrap_passes_with_demo_incentives_allowed() -> None:
    url = get_test_database_url()
    bootstrap_schema(url)
    errors = verify_schema(url, allow_demo_incentives=True)
    assert errors == []
