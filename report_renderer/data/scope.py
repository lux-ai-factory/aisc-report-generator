"""Scoping helpers: UUID checks and the name of a project's database."""
from __future__ import annotations

import re
import uuid

_DB_NAME = re.compile(r"^project_[0-9a-f]{32}$")


class NotInProject(LookupError):
    """The system version is not one of this project."""


def check_uuid(value) -> str:
    try:
        return str(uuid.UUID(str(value))).lower()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("not a UUID") from None


def database_name(pid) -> str:
    """The name of a project's own database: project_ + the pid's 32 hex characters."""
    name = "project_" + uuid.UUID(check_uuid(pid)).hex
    if not _DB_NAME.match(name):
        raise ValueError("not a project database name")
    return name
