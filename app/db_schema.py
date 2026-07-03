"""Production database schema verification for Kayak v1."""

from __future__ import annotations

import sys
from typing import Sequence

import psycopg

# Kayak v1 tables required after schema.sql + sql/migrations/*.sql + seed_plans.sql.
REQUIRED_TABLES: tuple[str, ...] = (
    "buildings",
    "listings",
    "listing_snapshots",
    "sources",
    "raw_documents",
    "floorplans",
    "units",
    "snapshot_concessions",
    "snapshot_fees",
    "crawl_runs",
    "incentives",
    "incentive_snapshots",
    "incentive_sources",
    "users",
    "refresh_tokens",
    "plans",
    "customer_entitlements",
    "checkout_sessions",
    "stripe_webhook_events",
    "alerts",
    "saved_buildings",
    "deal_report_unlocks",
    "concierge_requests",
)

REQUIRED_PLAN_CODES: tuple[str, ...] = (
    "free",
    "hunt_pass_30",
    "premium_plus_30",
    "concierge_one_time",
)

# Dev-only seed files — must never run in production bootstrap.
DEMO_SEED_FILES: frozenset[str] = frozenset(
    {
        "seed.sql",
        "seed_incentives.sql",
        "seed_real_data_pilot.sql",
    }
)

PRODUCTION_SAFE_SEED_FILES: frozenset[str] = frozenset({"seed_plans.sql"})


def missing_tables(conn: psycopg.Connection, tables: Sequence[str] = REQUIRED_TABLES) -> list[str]:
    rows = conn.execute(
        """
        SELECT t.table_name
        FROM information_schema.tables t
        WHERE t.table_schema = 'public'
          AND t.table_name = ANY(%s)
        """,
        (list(tables),),
    ).fetchall()
    present = {row[0] for row in rows}
    return [name for name in tables if name not in present]


def missing_plan_codes(
    conn: psycopg.Connection, codes: Sequence[str] = REQUIRED_PLAN_CODES
) -> list[str]:
    rows = conn.execute(
        "SELECT code FROM plans WHERE code = ANY(%s)",
        (list(codes),),
    ).fetchall()
    present = {row[0] for row in rows}
    return [code for code in codes if code not in present]


def demo_incentive_count(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*)::int FROM incentives WHERE is_demo = true"
    ).fetchone()
    return int(row[0]) if row else 0


def verify_production_schema(
    conn: psycopg.Connection,
    *,
    allow_demo_incentives: bool = False,
) -> list[str]:
    """Return human-readable errors; empty list means verification passed."""
    errors: list[str] = []

    missing = missing_tables(conn)
    if missing:
        errors.append(f"Missing tables: {', '.join(missing)}")

    missing_plans = missing_plan_codes(conn)
    if missing_plans:
        errors.append(f"Missing plan codes: {', '.join(missing_plans)}")

    demo_count = demo_incentive_count(conn)
    if not allow_demo_incentives and demo_count > 0:
        errors.append(f"Demo incentives present ({demo_count} rows with is_demo=true)")

    return errors


def verify_database_url(
    database_url: str,
    *,
    allow_demo_incentives: bool = False,
) -> list[str]:
    with psycopg.connect(database_url) as conn:
        return verify_production_schema(conn, allow_demo_incentives=allow_demo_incentives)


def assert_seed_file_allowed(filename: str, *, production: bool = True) -> None:
    """Raise ValueError if a seed SQL file must not run in the given context."""
    base = filename.rsplit("/", 1)[-1]
    if production and base in DEMO_SEED_FILES:
        raise ValueError(f"Demo seed file blocked in production: {base}")
    if production and base not in PRODUCTION_SAFE_SEED_FILES and base.startswith("seed"):
        raise ValueError(f"Non-production seed file blocked: {base}")


def main(argv: list[str] | None = None) -> int:
    import os

    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] != "verify":
        print(
            "Usage: python -m app.db_schema verify [DATABASE_URL]\n"
            "  Uses DATABASE_URL from the environment when the URL argument is omitted.",
            file=sys.stderr,
        )
        return 2

    database_url = args[1] if len(args) > 1 else os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: Set DATABASE_URL or pass a connection string.", file=sys.stderr)
        return 1

    allow_demo = os.environ.get("ALLOW_DEMO_INCENTIVES", "").lower() in ("1", "true", "yes")
    errors = verify_database_url(database_url, allow_demo_incentives=allow_demo)
    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print("OK: production schema verified")
    print(f"  tables: {len(REQUIRED_TABLES)} required tables present")
    print(f"  plans: {', '.join(REQUIRED_PLAN_CODES)}")
    if not allow_demo:
        print("  demo incentives: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
