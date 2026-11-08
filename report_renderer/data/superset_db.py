"""The project's charts and their review comments in the dashboard's database.

A chart belongs to a project when it sits on a dashboard shared with the project's role
(AiscProject_<hex>). Comments are keyed by the dashboard's id or slug; their time is UTC. A comment
deleted on the dashboard (deleted_at set) is left out, as the dashboard leaves it out.
"""
from __future__ import annotations

import uuid

from . import db
from .scope import check_uuid

_DASHBOARDS = ("SELECT DISTINCT d.id, d.slug FROM dashboards d"
               " JOIN dashboard_roles dr ON dr.dashboard_id = d.id JOIN ab_role r ON r.id = dr.role_id"
               " WHERE r.name = %(role)s")


def _role(project_id) -> str:
    return "AiscProject_" + uuid.UUID(check_uuid(project_id)).hex


def charts(project_id, system_id, *, sources) -> list[dict]:
    """The project's charts, the most recently changed first: what a report's chart list offers."""
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT DISTINCT s.id, s.slice_name, s.changed_on FROM slices s"
                   " JOIN dashboard_slices ds ON ds.slice_id = s.id"
                   f" WHERE ds.dashboard_id IN (SELECT id FROM ({_DASHBOARDS}) pd)"
                   " ORDER BY s.changed_on DESC NULLS LAST, s.id DESC",
                   {"role": _role(project_id)})


def chart(project_id, system_id, *, sources, chart_id) -> dict | None:
    return db.one(sources.superset_dsn, "superset",
                  "SELECT s.id, s.slice_name, s.viz_type, min(ds.dashboard_id) AS dashboard_id"
                  " FROM slices s JOIN dashboard_slices ds ON ds.slice_id = s.id"
                  f" WHERE s.id = %(c)s AND ds.dashboard_id IN (SELECT id FROM ({_DASHBOARDS}) pd)"
                  " GROUP BY s.id, s.slice_name, s.viz_type", {"role": _role(project_id), "c": int(chart_id)})


def export_blocks(project_id, system_id, *, sources) -> list[dict]:
    """The project's dashboards with plots saved with Save to report, by title: the tools a report shows a section of."""
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT d.id, d.dashboard_title FROM dashboards d"
                   f" WHERE d.id IN (SELECT id FROM ({_DASHBOARDS}) pd)"
                   " AND EXISTS (SELECT 1 FROM aisc_report_plot p WHERE p.dashboard_id = d.id)"
                   " ORDER BY d.dashboard_title, d.id",
                   {"role": _role(project_id)})


#: whether the plots' table has the rows column: the dashboard adds it when it starts, so an install whose dashboard has
#: not started since reads no count. pg_attribute is readable by every role, whatever its grants.
_HAS_ROWS = ("SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('aisc_report_plot')"
             " AND attname = 'rows' AND NOT attisdropped) AS present")


_HAS_SAVE_ID = ("SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('aisc_report_plot')"
                " AND attname = 'save_id' AND NOT attisdropped) AS present")

#: plots saved before saves carried an id count as one save when saved within this of the tool's newest plot
SAVED_TOGETHER = "60 seconds"


def exports(project_id, system_id, *, sources) -> list[dict]:
    """The plots of each dashboard's latest Save to report (one click saves several plots under one save id), in the
    order they were saved. A dashboard database whose plots carry no save id (saved before saves had one) takes the
    plots saved within SAVED_TOGETHER of the dashboard's newest as its latest save. rows is the number of rows the
    chart drew when the plot was saved, None when it was saved without one or the table predates the column."""
    params = {"role": _role(project_id)}
    with db.connect(sources.superset_dsn, "superset") as conn:
        rows = "p.rows" if conn.execute(_HAS_ROWS).fetchone()["present"] else "NULL::integer AS rows"
        save = "p.save_id" if conn.execute(_HAS_SAVE_ID).fetchone()["present"] else "NULL::text AS save_id"
        return list(conn.execute(
            "WITH plots AS (SELECT p.id, p.dashboard_id, d.dashboard_title, p.chart, p.tab, p.tags, p.svg, p.comment,"
            f" p.author_name, p.created_at, {rows}, {save}"
            " FROM aisc_report_plot p JOIN dashboards d ON d.id = p.dashboard_id"
            f" WHERE p.dashboard_id IN (SELECT id FROM ({_DASHBOARDS}) pd)),"
            " latest AS (SELECT DISTINCT ON (dashboard_id) dashboard_id, save_id, created_at FROM plots"
            " ORDER BY dashboard_id, created_at DESC, id DESC)"
            " SELECT p.* FROM plots p JOIN latest l ON l.dashboard_id = p.dashboard_id"
            " WHERE (l.save_id IS NOT NULL AND p.save_id = l.save_id)"
            f" OR (l.save_id IS NULL AND p.save_id IS NULL AND p.created_at >= l.created_at - interval '{SAVED_TOGETHER}')"
            " ORDER BY p.dashboard_title, p.created_at, p.id", params).fetchall())


def comments(project_id, system_id, *, sources, chart_id) -> list[dict]:
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT c.id, c.parent_id, c.author_name, c.body, c.created_at AT TIME ZONE 'UTC' AS created_at"
                   " FROM aisc_comment c WHERE c.chart_id = %(c)s AND c.deleted_at IS NULL"
                   f" AND c.dashboard_id IN (SELECT id::text FROM ({_DASHBOARDS}) pd"
                   f"                        UNION SELECT slug FROM ({_DASHBOARDS}) ps WHERE slug IS NOT NULL)"
                   " ORDER BY c.created_at, c.id", {"role": _role(project_id), "c": int(chart_id)})
