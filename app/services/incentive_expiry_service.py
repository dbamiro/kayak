"""Expire stale pending-review incentives."""

from __future__ import annotations

from psycopg import Connection


class IncentiveExpiryService:
    @staticmethod
    def expire_pending_incentives(conn: Connection, *, stale_days: int = 90) -> int:
        """
        Mark pending_review incentives as expired when:
        - expires_at is set and in the past, or
        - no expires_at and created_at older than stale_days.
        """
        days = max(int(stale_days), 1)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incentives
                SET status = 'expired', updated_at = now()
                WHERE status = 'pending_review'
                  AND (
                    (expires_at IS NOT NULL AND expires_at < now())
                    OR (
                      expires_at IS NULL
                      AND created_at < now() - (%s * interval '1 day')
                    )
                  )
                """,
                (days,),
            )
            n = cur.rowcount or 0
        conn.commit()
        return n
