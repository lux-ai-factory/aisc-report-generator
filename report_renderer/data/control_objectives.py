"""The objectives assessment of the pinned version.

Every read goes to the project's own database, so the database itself is the project filter; queries
still filter by version. A missing database, schema or table reads as nothing.
"""
from __future__ import annotations

import psycopg

from ..objective_order import objective_order
from ..rating import band, rating
from . import db
from .scope import check_uuid

_SCOPE = "a.system_id = %(s)s"


def _params(project_id, system_id) -> dict:
    return {"s": check_uuid(system_id)}


def assessment(project_id, system_id, *, sources) -> dict | None:
    return db.project_one(sources, check_uuid(project_id), "control_objectives",
                  f"SELECT a.id, a.name FROM control_objectives.project a WHERE {_SCOPE}",
                  _params(project_id, system_id))


def _rated(row: dict) -> dict:
    out = dict(row)
    impact, likelihood = out.pop("rating_impact"), out.pop("rating_likelihood")
    value = rating(impact, likelihood)
    return out | {"impact": impact, "likelihood": likelihood, "rating": value, "band": band(value)}


def mappings(project_id, system_id, *, sources) -> list[dict]:
    """One row per (risk, mapped objective), with the risk's impact, likelihood, rating and band."""
    rows = db.project_rows(sources, check_uuid(project_id), "control_objectives",
                   "SELECT r.risk_id, r.position, r.text, r.short_label, r.rating_impact, r.rating_likelihood,"
                   " m.objective_id, m.quote, m.rationale"
                   " FROM control_objectives.risk r JOIN control_objectives.project a ON a.id = r.project_id"
                   " LEFT JOIN control_objectives.mapped_objective m ON m.risk_row_id = r.id"
                   f" WHERE {_SCOPE} ORDER BY r.position, m.objective_id", _params(project_id, system_id))
    return [_rated(r) for r in rows]


def mapping_run(project_id, system_id, *, sources) -> dict | None:
    return db.project_one(sources, check_uuid(project_id), "control_objectives",
                  "SELECT mr.stop, mr.ran_at FROM control_objectives.mapping_run mr"
                  " JOIN control_objectives.project a ON a.id = mr.project_id"
                  f" WHERE {_SCOPE} ORDER BY mr.ran_at DESC LIMIT 1", _params(project_id, system_id))


def newest_newer_assessment(project_id, system_id, *, sources) -> int | None:
    row = db.project_one(sources, check_uuid(project_id), "control_objectives",
                 "SELECT max(s.number) AS n FROM control_objectives.project a JOIN project.system s ON s.pid = a.system_id"
                 " WHERE s.number > (SELECT number FROM project.system WHERE pid = %(s)s)",
                 _params(project_id, system_id))
    return row["n"] if row else None


def objective_ids(project_id, system_id, *, sources) -> list[str]:
    """The objectives the report is about: those selected in step 2 for the version, or, when its assessment has no selection (or the table is not there), the mapped ones."""
    chosen = db.project_one(sources, check_uuid(project_id), "control_objectives",
                            "SELECT sel.objective_ids FROM control_objectives.objective_selection sel"
                            " JOIN control_objectives.project a ON a.id = sel.project_id"
                            f" WHERE {_SCOPE}", _params(project_id, system_id))
    if chosen is not None:
        return sorted(chosen["objective_ids"], key=objective_order)
    rows = db.project_rows(sources, check_uuid(project_id), "control_objectives",
                   "SELECT DISTINCT m.objective_id FROM control_objectives.mapped_objective m"
                   " JOIN control_objectives.risk r ON r.id = m.risk_row_id"
                   " JOIN control_objectives.project a ON a.id = r.project_id"
                   f" WHERE {_SCOPE} ORDER BY m.objective_id", _params(project_id, system_id))
    return sorted((r["objective_id"] for r in rows), key=objective_order)


def priority_ids(project_id, system_id, *, sources) -> list[str]:
    """The version's priority objectives as step 2 stores them on its selection (its default rule with the
    assessor's choices over it). [] when there is no selection, or a database without the column."""
    try:
        row = db.project_one(sources, check_uuid(project_id), "control_objectives",
                             "SELECT sel.priority_ids FROM control_objectives.objective_selection sel"
                             " JOIN control_objectives.project a ON a.id = sel.project_id"
                             f" WHERE {_SCOPE}", _params(project_id, system_id))
    except psycopg.errors.UndefinedColumn:
        return []
    return sorted((row or {}).get("priority_ids") or [], key=objective_order)


def own_objectives(project_id, system_id, *, sources) -> list[dict]:
    """The project's own objectives the version's assessment works with: those of the profile version it
    pins, worded as in the set version that profile took. [] for an assessment on the built-in profile,
    or for a database without the objective set columns."""
    try:
        return db.project_rows(sources, check_uuid(project_id), "control_objectives",
            "SELECT pi.objective_id, si.dimension, si.label, si.text, si.legal_basis"
            " FROM control_objectives.project a"
            " JOIN control_objectives.objective_profile_version_item pi ON pi.profile_version_id = a.profile_version_id"
            " JOIN control_objectives.objective_set os ON os.code = pi.set_code"
            " JOIN control_objectives.objective_set_version sv ON sv.set_id = os.id AND sv.number = pi.set_version_number"
            " JOIN control_objectives.objective_set_version_item si"
            "   ON si.set_version_id = sv.id AND si.objective_id = pi.objective_id"
            f" WHERE {_SCOPE} ORDER BY pi.position", _params(project_id, system_id))
    except psycopg.errors.UndefinedColumn:
        return []
