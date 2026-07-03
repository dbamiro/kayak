"""Bootstrap and reset the isolated Kayak pytest database."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

import psycopg
from psycopg import sql

from app.db_schema import verify_production_schema

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
TEST_SEED = Path(__file__).resolve().parent / "fixtures" / "test_seed.sql"
PRODUCTION_SEED = SQL_DIR / "seed_plans.sql"

DEFAULT_TEST_DATABASE_URL = "postgresql://dmv_user:dmv_pass@localhost:5432/kayak_test"


def get_test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def admin_database_url(test_url: str) -> str:
    """Connect to maintenance DB (postgres) to create the test database."""
    parsed = urlparse(test_url)
    return urlunparse(parsed._replace(path="/postgres"))


def postgres_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        with psycopg.connect(url, connect_timeout=timeout) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def ensure_database_exists(test_url: str) -> None:
    db_name = urlparse(test_url).path.lstrip("/") or "kayak_test"
    admin_url = admin_database_url(test_url)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        ).fetchone()
        if not row:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))


def _apply_sql_file(conn: psycopg.Connection, path: Path) -> None:
    sql_text = path.read_text(encoding="utf-8")
    conn.execute(sql_text)


def schema_bootstrapped(conn: psycopg.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'buildings'"
    ).fetchone()
    return row is not None


def bootstrap_schema(test_url: str) -> None:
    """Apply schema.sql + migrations (idempotent). Safe for empty kayak_test DB."""
    ensure_database_exists(test_url)
    with psycopg.connect(test_url, autocommit=True) as conn:
        if not schema_bootstrapped(conn):
            _apply_sql_file(conn, SQL_DIR / "schema.sql")
        migrations = sorted(SQL_DIR.glob("migrations/*.sql"))
        for migration in migrations:
            _apply_sql_file(conn, migration)


def bootstrap_production_schema(test_url: str) -> None:
    """Production path: schema + migrations + seed_plans.sql (no demo seeds)."""
    ensure_database_exists(test_url)
    with psycopg.connect(test_url, autocommit=True) as conn:
        if not schema_bootstrapped(conn):
            _apply_sql_file(conn, SQL_DIR / "schema.sql")
        for migration in sorted(SQL_DIR.glob("migrations/*.sql")):
            _apply_sql_file(conn, migration)
        _apply_sql_file(conn, PRODUCTION_SEED)


def verify_schema(test_url: str, *, allow_demo_incentives: bool = False) -> list[str]:
    with psycopg.connect(test_url) as conn:
        return verify_production_schema(conn, allow_demo_incentives=allow_demo_incentives)


def reset_test_data(test_url: str) -> None:
    """Truncate all app tables and load deterministic test seed."""
    bootstrap_schema(test_url)
    with psycopg.connect(test_url, autocommit=True) as conn:
        conn.execute(
            """
            TRUNCATE TABLE
                incentive_snapshots,
                incentives,
                incentive_sources,
                snapshot_concessions,
                snapshot_fees,
                listing_snapshots,
                listings,
                units,
                floorplans,
                raw_documents,
                raw_captures,
                customer_entitlements,
                checkout_sessions,
                deal_report_unlocks,
                concierge_requests,
                refresh_tokens,
                alerts,
                saved_buildings,
                stripe_webhook_events,
                crawl_runs,
                sources,
                buildings,
                users,
                plans
            RESTART IDENTITY CASCADE
            """
        )
        _apply_sql_file(conn, TEST_SEED)


def bootstrap_test_database(test_url: str | None = None) -> str:
    url = test_url or get_test_database_url()
    bootstrap_schema(url)
    reset_test_data(url)
    return url
