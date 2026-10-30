"""Step 4's Evidence map of the pinned version, in the project's database project_<hex>.

The map's links reach the renderer in the snapshot (`coverage_links`, copied by the composer); what is read
here is who reviewed the map (evidence.review: a second person; a change to the map clears it). A database
without the table reads as no review.
"""
from __future__ import annotations

from . import db
from .scope import check_uuid


def review(project_id, system_id, *, sources) -> dict | None:
    """{reviewed_by_name, reviewed_at} of the version's map, or None when it is not reviewed."""
    found = db.project_rows(sources, check_uuid(project_id), "evidence",
                            "SELECT reviewed_by_name, reviewed_at FROM evidence.review WHERE system_id = %(s)s",
                            {"s": check_uuid(system_id)})
    return found[0] if found else None
