"""The project and its system versions.

The platform database is read for core.project (and pg_database) only. The card versions are
project.system of the project's own database: a version that is not there is NotInProject (404), and
a project whose database (or whose project.system) is missing has no data at all, so its report is
drawn from a stand-in version and every data block reads as empty.
"""
from __future__ import annotations

from . import db
from .scope import NotInProject, check_uuid

_VERSION = "SELECT pid::text, number, name, version, provider, description, created_at FROM project.system"


def _without_database(p: str, s: str) -> dict:
    """The pinned version of a project that has no database (or no project.system in it) yet: nothing
    is known of it, so it has no number, name or description, and nothing can be read for it."""
    return {"pid": s, "project_id": p, "number": 0, "name": "", "version": None, "provider": None,
            "description": None, "created_at": None}


def pinned_system(project_id, system_id, *, sources) -> dict:
    try:
        p, s = check_uuid(project_id), check_uuid(system_id)
    except ValueError:
        raise NotInProject("the system is not a version of this project") from None
    dsn = db.project_dsn(sources, p)
    if dsn is None:
        return _without_database(p, s)
    try:
        row = db.one(dsn, "project", _VERSION + " WHERE pid = %(s)s", {"s": s})
    except db._ABSENT:
        return _without_database(p, s)
    if row is None:
        raise NotInProject("the system is not a version of this project")
    row = dict(row)
    row["project_id"] = p
    return row


def project(project_id, system_id, *, sources) -> dict:
    return db.one(sources.platform_dsn, "platform",
                  "SELECT pid::text, name, slug FROM core.project WHERE pid = %(p)s", {"p": check_uuid(project_id)})


def newer_versions(project_id, system_id, *, sources) -> list[dict]:
    return db.project_rows(sources, check_uuid(project_id), "project",
                           "SELECT pid::text, number FROM project.system"
                           " WHERE number > (SELECT number FROM project.system WHERE pid = %(s)s)"
                           " ORDER BY number", {"s": check_uuid(system_id)})


def older_versions(project_id, system_id, *, sources) -> list[dict]:
    """The project's versions numbered below the pinned one, newest first."""
    return db.project_rows(sources, check_uuid(project_id), "project",
                           "SELECT pid::text, number, version FROM project.system"
                           " WHERE number < (SELECT number FROM project.system WHERE pid = %(s)s)"
                           " ORDER BY number DESC", {"s": check_uuid(system_id)})


def versions(project_id, system_id, *, sources) -> list[dict]:
    """Every version of the project, oldest first, with the moment it was saved: a comment is matched
    to the version current when it was written."""
    return db.project_rows(sources, check_uuid(project_id), "project",
                           "SELECT pid::text, number, created_at FROM project.system ORDER BY created_at, number", {})
