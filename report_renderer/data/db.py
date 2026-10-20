"""The one place that opens database connections.

A connection failure never carries the DSN: it becomes SourceUnavailable(source).

One database per project: a project's versions and module data live
in its own database `project_<hex>`. `project_rows` and `project_one` find that database through
`pg_database` on the platform database, and read nothing (`[]`, `None`) when the database is missing or
when a module's schema or table is not there, never an error.
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from ..errors import SourceUnavailable
from .scope import database_name

#: a module schema or table that is not (yet) in a project database reads as nothing
_ABSENT = (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName)


@contextmanager
def connect(dsn: str, source: str):
    try:
        conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError:
        raise SourceUnavailable(source) from None
    try:
        yield conn
    finally:
        conn.close()


def rows(dsn: str, source: str, sql: str, params=None) -> list[dict]:
    with connect(dsn, source) as conn:
        return list(conn.execute(sql, params or {}).fetchall())


def one(dsn: str, source: str, sql: str, params=None) -> dict | None:
    with connect(dsn, source) as conn:
        return conn.execute(sql, params or {}).fetchone()


#: How long whether a project's database exists is remembered: every read asked, one more connection
#: each, and a report reads many times. A database made or dropped is noticed within this time.
PROJECT_DSN_TTL_S = 30.0
_DSN_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}


def _now() -> float:
    import time

    return time.monotonic()


def project_dsn(sources, project_id) -> str | None:
    """The DSN of the project's own database, or None when that database does not exist."""
    name = database_name(project_id)
    key = (sources.platform_dsn, name)
    seen = _DSN_CACHE.get(key)
    if seen is not None and _now() - seen[0] < PROJECT_DSN_TTL_S:
        exists = seen[1]
    else:
        exists = one(sources.platform_dsn, "platform", "SELECT 1 AS x FROM pg_database WHERE datname = %(n)s",
                     {"n": name}) is not None
        _DSN_CACHE[key] = (_now(), exists)
    return sources.project_dsn(name) if exists else None


def project_rows(sources, project_id, source: str, sql: str, params=None) -> list[dict]:
    """Rows from the project's own database; [] when it, or the schema or table read, is missing."""
    dsn = project_dsn(sources, project_id)
    if dsn is None:
        return []
    try:
        return rows(dsn, source, sql, params)
    except _ABSENT:
        return []


def project_one(sources, project_id, source: str, sql: str, params=None) -> dict | None:
    """One row from the project's own database; None when it, or the schema or table read, is missing."""
    dsn = project_dsn(sources, project_id)
    if dsn is None:
        return None
    try:
        return one(dsn, source, sql, params)
    except _ABSENT:
        return None
