"""The engine's test results of the pinned version.

Every query reads the project's own database, which is the project scope, and, except the count of unversioned evaluations, is scoped by the pinned version
(engine.aisc_backend_evaluation.system_id). A missing database, schema or table reads as nothing.
The tables carry the engine's Django names (aisc_backend_*). Explicit column lists only; the plugin
config table only by its id, plugin_id and name (the config may hold tool settings, and the report
login may not read it: see aisc's scripts/report-grants.sh).

A report's selection narrows the runs to a period of
their created_at and, with other_versions, widens them to every version's runs (and the unversioned).
`selection=None` is the pinned version's runs, all of them.
"""
from __future__ import annotations

from ..selection import Selection
from . import db
from .scope import check_uuid

_EVAL = "engine.aisc_backend_evaluation e"


#: every run of the project, whatever its version: the scope of the tool and metric choices
_EVERY_VERSION = Selection(other_versions=True)


def _scope(selection) -> str:
    """The runs a report covers: the pinned version's (or every version's) inside the period."""
    version = "TRUE" if (selection is not None and selection.other_versions) else "e.system_id = %(s)s"
    return (f"{version} AND (%(pf)s::timestamptz IS NULL OR e.created_at >= %(pf)s::timestamptz)"
            " AND (%(pt)s::timestamptz IS NULL OR e.created_at < %(pt)s::timestamptz)")


def _params(project_id, system_id, selection=None, **extra) -> dict:
    return {"s": check_uuid(system_id), "pf": getattr(selection, "period_from", None),
            "pt": getattr(selection, "period_to", None), **extra}


class LocalRunRefused(ValueError):
    """A run on a local model file was asked for by id."""


def _local(run: str) -> str:
    """SQL: the plugin run aliased `run` is on a local model file (the engine worker stores
    {"local_model": {...}} as the value of the plugin's model input). Such a run is not part of the
    assessment record, so no query below returns it, its inputs, artifacts or observations."""
    return ("EXISTS (SELECT 1 FROM engine.aisc_backend_evaluationinput li"
            f" WHERE li.evaluation_plugin_id = {run}.id AND li.value ? 'local_model')")


def _local_observation(o: str) -> str:
    """SQL: observation `o` belongs to a local run, found as the engine tags it: "{package}::{name} (v{version})"
    in its evaluation."""
    return ("EXISTS (SELECT 1 FROM engine.aisc_backend_evaluationplugin lp"
            " JOIN engine.aisc_backend_pluginconfig lc ON lc.id = lp.plugin_config_id"
            " JOIN engine.aisc_backend_plugin lq ON lq.id = lc.plugin_id"
            f" WHERE lp.evaluation_id = {o}.evaluation_id"
            f" AND {o}.tool = lq.package_name || '::' || lq.name || ' (v' || lq.version || ')' AND {_local('lp')})")


def _only_local(ev: str = "e") -> str:
    """SQL: evaluation `ev` has plugin runs and every one is local, so nothing of it is in the record."""
    return ("(EXISTS (SELECT 1 FROM engine.aisc_backend_evaluationplugin lp WHERE lp.evaluation_id = "
            f"{ev}.id) AND NOT EXISTS (SELECT 1 FROM engine.aisc_backend_evaluationplugin cp WHERE "
            f"cp.evaluation_id = {ev}.id AND NOT {_local('cp')}))")


def evaluations(project_id, system_id, *, sources, statuses=None, pids=None, selection=None) -> list[dict]:
    """The evaluations a report covers. A run on a local model file is not part of the assessment record: no
query here returns it, and an evaluation whose runs are all local is left out of a selection and refused when
asked for by pid. An evaluation that also has a card run stays, with the card run alone."""
    rows = db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT e.id, e.pid::text AS pid, e.status, e.created_at, s.number AS version_number,"
                   f" {_only_local()} AS local"
                   f" FROM {_EVAL} LEFT JOIN project.system s ON s.pid = e.system_id WHERE {_scope(selection)}"
                   " AND (%(st)s::text[] IS NULL OR e.status = ANY(%(st)s::text[]))"
                   " AND (%(pids)s::uuid[] IS NULL OR e.pid = ANY(%(pids)s::uuid[]))"
                   " ORDER BY e.created_at, e.id",
                   _params(project_id, system_id, selection, st=list(statuses) if statuses is not None else None,
                           pids=[check_uuid(x) for x in pids] if pids is not None else None))
    if pids is not None and any(r["local"] for r in rows):
        raise LocalRunRefused("a local run is not part of the assessment record")
    return [{k: v for k, v in r.items() if k != "local"} for r in rows if not r["local"]]


def runs(project_id, system_id, *, sources, evaluation_ids, selection=None) -> list[dict]:
    if not evaluation_ids:
        return []
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT ep.id, ep.pid::text AS pid, ep.name, ep.status, ep.evaluation_id, pl.display_name,"
                   " pl.name AS plugin_name, pl.package_name, pl.version, pc.id AS plugin_config_id"
                   f" FROM engine.aisc_backend_evaluationplugin ep JOIN {_EVAL} ON e.id = ep.evaluation_id"
                   " LEFT JOIN engine.aisc_backend_pluginconfig pc ON pc.id = ep.plugin_config_id"
                   " LEFT JOIN engine.aisc_backend_plugin pl ON pl.id = pc.plugin_id"
                   f" WHERE {_scope(selection)} AND NOT {_local('ep')} AND e.id = ANY(%(ids)s::bigint[])"
                   " ORDER BY ep.evaluation_id, ep.id",
                   _params(project_id, system_id, selection, ids=list(evaluation_ids)))


def inputs(project_id, system_id, *, sources, run_ids, selection=None) -> list[dict]:
    if not run_ids:
        return []
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT ei.evaluation_plugin_id, ei.name AS input_name, c.name, c.component_type,"
                   " c.pid::text AS component_pid"
                   " FROM engine.aisc_backend_evaluationinput ei"
                   " JOIN engine.aisc_backend_aicomponent c ON c.id = ei.component_id"
                   " JOIN engine.aisc_backend_evaluationplugin ep ON ep.id = ei.evaluation_plugin_id"
                   f" JOIN {_EVAL} ON e.id = ep.evaluation_id"
                   f" WHERE {_scope(selection)} AND NOT {_local('ep')} AND ep.id = ANY(%(ids)s::bigint[])"
                   " ORDER BY ei.evaluation_plugin_id, ei.id",
                   _params(project_id, system_id, selection, ids=list(run_ids)))


#: the engine input that names what a run assessed
TARGET_INPUT = "target"


def targets(project_id, system_id, *, sources) -> list[dict]:
    """The project's targets (target.target, platform-owned): the system and each card component, with the
    engine component that mirrors each. Nothing when the project has no target table yet."""
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT t.key, t.kind, t.component_kind, t.label, t.first_card_number, t.last_card_number,"
                   " t.engine_component::text AS engine_component FROM target.target t"
                   " ORDER BY t.kind DESC, t.label, t.key", {})


def latest_card_number(project_id, system_id, *, sources) -> int | None:
    """The number of the project's latest version (its latest card)."""
    row = db.project_one(sources, check_uuid(project_id), "engine",
                 "SELECT max(number) AS n FROM project.system", {})
    return row["n"] if row else None


def observations(project_id, system_id, *, sources, evaluation_ids, selection=None) -> list[dict]:
    if not evaluation_ids:
        return []
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT o.id, o.evaluation_id, o.tool FROM engine.aisc_backend_observation o"
                   f" JOIN {_EVAL} ON e.id = o.evaluation_id"
                   f" WHERE {_scope(selection)} AND NOT {_local_observation('o')} AND e.id = ANY(%(ids)s::bigint[])"
                   " ORDER BY o.evaluation_id, o.id",
                   _params(project_id, system_id, selection, ids=list(evaluation_ids)))


def measurements(project_id, system_id, *, sources, observation_ids, selection=None) -> list[dict]:
    if not observation_ids:
        return []
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT m.observation_id, m.name, mt.name AS metric, m.score, m.unit, m.uncertainty,"
                   " m.dimensions, m.direction, m.description, m.error"
                   " FROM engine.aisc_backend_measurement m JOIN engine.aisc_backend_metric mt ON mt.id = m.metric_id"
                   " JOIN engine.aisc_backend_observation o ON o.id = m.observation_id"
                   f" JOIN {_EVAL} ON e.id = o.evaluation_id"
                   f" WHERE {_scope(selection)} AND NOT {_local_observation('o')} AND o.id = ANY(%(ids)s::bigint[])"
                   " ORDER BY m.observation_id, m.id",
                   _params(project_id, system_id, selection, ids=list(observation_ids)))


def artifacts(project_id, system_id, *, sources, run_ids, selection=None) -> list[dict]:
    if not run_ids:
        return []
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT a.evaluation_plugin_id, a.name, a.file_size FROM engine.aisc_backend_artifact a"
                   " JOIN engine.aisc_backend_evaluationplugin ep ON ep.id = a.evaluation_plugin_id"
                   f" JOIN {_EVAL} ON e.id = ep.evaluation_id"
                   f" WHERE {_scope(selection)} AND NOT {_local('ep')} AND ep.id = ANY(%(ids)s::bigint[])"
                   " ORDER BY a.evaluation_plugin_id, a.id",
                   _params(project_id, system_id, selection, ids=list(run_ids)))


def run_details(project_id, system_id, *, sources, evaluation_ids, selection=None) -> list[dict]:
    """The tool runs of these evaluations with their times and the name of their configuration (the
    Test runs block); never the configuration's settings."""
    if not evaluation_ids:
        return []
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT ep.evaluation_id, ep.name, pl.display_name, ep.status, ep.started_at, ep.finished_at,"
                   " pc.name AS config_name"
                   f" FROM engine.aisc_backend_evaluationplugin ep JOIN {_EVAL} ON e.id = ep.evaluation_id"
                   " LEFT JOIN engine.aisc_backend_pluginconfig pc ON pc.id = ep.plugin_config_id"
                   " LEFT JOIN engine.aisc_backend_plugin pl ON pl.id = pc.plugin_id"
                   f" WHERE {_scope(selection)} AND NOT {_local('ep')} AND e.id = ANY(%(ids)s::bigint[])"
                   " ORDER BY ep.started_at, ep.id",
                   _params(project_id, system_id, selection, ids=list(evaluation_ids)))


def unversioned_count(project_id, system_id, *, sources) -> int:
    row = db.project_one(sources, check_uuid(project_id), "engine",
                 f"SELECT count(*) AS n FROM engine.aisc_backend_evaluation e WHERE e.system_id IS NULL AND NOT {_only_local()}",
                 _params(project_id, system_id))
    return int(row["n"]) if row else 0


def newest_newer_evaluation(project_id, system_id, *, sources) -> int | None:
    row = db.project_one(sources, check_uuid(project_id), "engine",
                 f"SELECT max(s.number) AS n FROM {_EVAL} JOIN project.system s ON s.pid = e.system_id"
                 f" WHERE s.number > (SELECT number FROM project.system WHERE pid = %(s)s) AND NOT {_only_local()}",
                 _params(project_id, system_id))
    return row["n"] if row else None


def metric_pairs(project_id, system_id, *, sources) -> list[dict]:
    """The distinct (tool, metric) of every run of the project, of any status and any version, named as
    the Test results block names them (views.load_runs): a run owns the observations tagged
    "{package_name}::{plugin name} (v{version})" in its evaluation, or, when it is its evaluation's only
    run and owns none, all of them; an observation no run owns is left out. The tool is the plugin's
    display name, else the plugin's name, else (no plugin configuration) the run's name; the metric is
    the metric's name, else the measurement's. Empty names are left out."""
    return db.project_rows(sources, check_uuid(project_id), "engine",
                   "WITH r AS ("
                   " SELECT ep.id, ep.evaluation_id,"
                   " COALESCE(NULLIF(pl.display_name, ''), NULLIF(pl.name, ''), ep.name) AS tool,"
                   " CASE WHEN NULLIF(pl.name, '') IS NOT NULL THEN COALESCE(pl.package_name, 'None') || '::'"
                   " || pl.name || ' (v' || COALESCE(pl.version, 'None') || ')' END AS tag,"
                   " count(*) OVER (PARTITION BY ep.evaluation_id) AS runs_of_evaluation"
                   " FROM engine.aisc_backend_evaluationplugin ep"
                   f" JOIN {_EVAL} ON e.id = ep.evaluation_id"
                   " LEFT JOIN engine.aisc_backend_pluginconfig pc ON pc.id = ep.plugin_config_id"
                   " LEFT JOIN engine.aisc_backend_plugin pl ON pl.id = pc.plugin_id"
                   f" WHERE {_scope(_EVERY_VERSION)} AND NOT {_local('ep')}),"
                   " owned AS ("
                   " SELECT r.tool, o.id AS observation_id FROM r JOIN engine.aisc_backend_observation o"
                   f" ON o.evaluation_id = r.evaluation_id AND o.tool = r.tag AND NOT {_local_observation('o')}"
                   " UNION ALL"
                   " SELECT r.tool, o.id FROM r JOIN engine.aisc_backend_observation o ON o.evaluation_id = r.evaluation_id"
                   f" WHERE r.runs_of_evaluation = 1 AND NOT {_local_observation('o')} AND NOT EXISTS (SELECT 1 FROM engine.aisc_backend_observation t"
                   " WHERE t.evaluation_id = r.evaluation_id AND t.tool = r.tag))"
                   " SELECT DISTINCT owned.tool, COALESCE(NULLIF(mt.name, ''), m.name) AS metric FROM owned"
                   " JOIN engine.aisc_backend_measurement m ON m.observation_id = owned.observation_id"
                   " JOIN engine.aisc_backend_metric mt ON mt.id = m.metric_id"
                   " WHERE NULLIF(owned.tool, '') IS NOT NULL AND NULLIF(COALESCE(NULLIF(mt.name, ''), m.name), '') IS NOT NULL",
                   _params(project_id, system_id))


def tool_choices(project_id, system_id, *, sources) -> list[dict]:
    """Every tool the project's runs used, of any version: a layout naming a tool holds for every version."""
    rows = db.project_rows(sources, check_uuid(project_id), "engine",
                   "SELECT DISTINCT pl.display_name FROM engine.aisc_backend_evaluationplugin ep"
                   f" JOIN {_EVAL} ON e.id = ep.evaluation_id"
                   " JOIN engine.aisc_backend_pluginconfig pc ON pc.id = ep.plugin_config_id"
                   " JOIN engine.aisc_backend_plugin pl ON pl.id = pc.plugin_id"
                   f" WHERE {_scope(_EVERY_VERSION)} AND NOT {_local('ep')} AND pl.display_name IS NOT NULL ORDER BY pl.display_name",
                   _params(project_id, system_id))
    return [{"value": r["display_name"], "label": r["display_name"]} for r in rows]
