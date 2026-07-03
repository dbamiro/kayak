"""Batch data-quality scan — extend logic shared with GET /admin/data-quality."""

from __future__ import annotations

from psycopg.rows import dict_row

from app.db import get_pool


def main() -> None:
    pool = get_pool()
    n = 0
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM sources s
                WHERE s.active = true
                  AND (s.last_crawl_at IS NULL OR s.last_crawl_at < now() - interval '7 days')
                """
            )
            row = cur.fetchone()
            n = int(row["c"]) if row else 0
    print(f"stale_active_sources_count={n}")


if __name__ == "__main__":
    main()
