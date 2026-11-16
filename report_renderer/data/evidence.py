"""Step 4's Evidence map of the pinned version, in the project's database project_<hex>.

The map's links reach the renderer in the snapshot (`coverage_links`, copied by the composer); what is read
here is who reviewed the map (evidence.review: a second person; a change to the map ends the review, which
stays on record with voided_at set). A database without the table reads as no review.
"""
from __future__ import annotations

from . import db
from .scope import check_uuid


def review(project_id, system_id, *, sources) -> dict | None:
    """{reviewed_by_name, reviewed_at} of the version's map, or None when it is not reviewed."""
    # a review a later change of the map ended stays on record with voided_at set; read through to_jsonb so a
    # database from before that column reads every row as holding
    found = db.project_rows(sources, check_uuid(project_id), "evidence",
                            "SELECT reviewed_by_name, reviewed_at FROM evidence.review r WHERE system_id = %(s)s"
                            " AND to_jsonb(r) ->> 'voided_at' IS NULL ORDER BY reviewed_at DESC LIMIT 1",
                            {"s": check_uuid(system_id)})
    return found[0] if found else None
