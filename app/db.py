from collections.abc import Generator

from psycopg_pool import ConnectionPool

from app.config import get_settings


_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": False},
            open=True,  # explicit: future psycopg_pool releases default to open=False
        )
    return _pool


def get_db() -> Generator:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
