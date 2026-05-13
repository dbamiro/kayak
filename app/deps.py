from typing import Annotated

from fastapi import Depends
from psycopg import Connection

from app.db import get_pool


def get_conn():
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


ConnDep = Annotated[Connection, Depends(get_conn)]
