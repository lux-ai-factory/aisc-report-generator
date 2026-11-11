"""The AI card of the pinned version, from the qualification module.

Read only; the knowledge graph and the risk chains are AIRO tables, never written. Every read goes to
the project's own database, so the database itself is the project filter; queries still filter by
version. A missing database, schema or table reads as nothing.
"""
from __future__ import annotations

from . import db
from .scope import check_uuid

#: the card of the version at the pinned revision: the highest revision not above the pin
_SCOPE = ("q.system_id = %(s)s AND q.revision = (SELECT max(o.revision) FROM qualification.qualification o"
          " WHERE o.system_id = %(s)s AND o.revision <= %(r)s)")


def _params(project_id, system_id, revision=None) -> dict:
    out = {"s": check_uuid(system_id)}
    if revision is not None:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("the card revision is a whole number from 1")
        out["r"] = revision
    return out


def card(project_id, system_id, *, sources, revision: int) -> dict | None:
    return db.project_one(sources, check_uuid(project_id), "qualification",
                  'SELECT q.id, q."systemName" AS system_name, q."systemVersion" AS system_version, q.company,'
                  ' q.revision, q.description, q."targetUseCase" AS target_use_case, q."targetUsers" AS target_users,'
                  ' q."intendedDeployers" AS intended_deployers, q."targetSystemTags" AS target_system_tags,'
                  ' q."sectorTags" AS sector_tags, q."marketFormTags" AS market_form_tags,'
                  ' q."localityTags" AS locality_tags, q.system_type, q.purpose'
                  f" FROM qualification.qualification q WHERE {_SCOPE}", _params(project_id, system_id, revision))


def components(project_id, system_id, *, sources, revision: int) -> list[dict]:
    return db.project_rows(sources, check_uuid(project_id), "qualification",
                   "SELECT c.name, c.component_type, c.airo_property, c.object_name"
                   " FROM qualification.card_component c JOIN qualification.qualification q ON q.id = c.qualification_id"
                   f" WHERE {_SCOPE} ORDER BY c.linked_at, c.name", _params(project_id, system_id, revision))


def knowledge_graph(project_id, system_id, *, sources, revision: int) -> dict | None:
    return db.project_one(sources, check_uuid(project_id), "qualification",
                  "SELECT k.digest, k.jsonld, k.nodes, k.triples, k.built_at"
                  ' FROM qualification.knowledge_graph k JOIN qualification.qualification q ON q.id = k."qualificationId"'
                  f" WHERE {_SCOPE}", _params(project_id, system_id, revision))


def risks(project_id, system_id, *, sources, revision: int) -> list[dict]:
    return db.project_rows(sources, check_uuid(project_id), "qualification",
                   'SELECT r.position, r.risk, r.source, r.vulnerability, r.consequence, r.affected,'
                   ' r."impactAreas" AS impact_areas, r.source_term, r.consequence_term, r.impact_term'
                   ' FROM qualification.qualification_risk r JOIN qualification.qualification q'
                   ' ON q.id = r."qualificationId"'
                   f" WHERE {_SCOPE} ORDER BY r.position", _params(project_id, system_id, revision))


def newest_newer_card(project_id, system_id, *, sources) -> int | None:
    row = db.project_one(sources, check_uuid(project_id), "qualification",
                 "SELECT max(s.number) AS n FROM qualification.qualification q JOIN project.system s ON s.pid = q.system_id"
                 " WHERE s.number > (SELECT number FROM project.system WHERE pid = %(s)s)", _params(project_id, system_id))
    return row["n"] if row else None


def amendments(project_id, system_id, *, sources, revision: int) -> list[dict]:
    """The corrections of the card up to the pinned revision, oldest first: one row per revision above 1."""
    return db.project_rows(sources, check_uuid(project_id), "qualification",
                           "SELECT q.revision, q.amend_reason AS reason, q.amend_requested_by AS requested_by,"
                           " q.created_at FROM qualification.qualification q"
                           " WHERE q.system_id = %(s)s AND q.revision > 1 AND q.revision <= %(r)s"
                           " ORDER BY q.revision", _params(project_id, system_id, revision))
