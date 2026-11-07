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
    """The project's dashboards, by title: what a report can show saved pictures of."""
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT d.id, d.dashboard_title FROM dashboards d"
                   f" WHERE d.id IN (SELECT id FROM ({_DASHBOARDS}) pd) ORDER BY d.dashboard_title, d.id",
                   {"role": _role(project_id)})


#: whether the plots' table has the rows column: the dashboard adds it when it starts, so an install whose dashboard has
#: not started since reads no count. pg_attribute is readable by every role, whatever its grants.
_HAS_ROWS = ("SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('aisc_report_plot')"
             " AND attname = 'rows' AND NOT attisdropped) AS present")


def exports(project_id, system_id, *, sources) -> list[dict]:
    """The plots saved with Save to report on the project's dashboards: the newest per dashboard, chart and filters, in
    the order they were saved. rows is the number of rows the chart drew when the plot was saved, None when it was
    saved without one or the table predates the column."""
    params = {"role": _role(project_id)}
    with db.connect(sources.superset_dsn, "superset") as conn:
        rows = "p.rows" if conn.execute(_HAS_ROWS).fetchone()["present"] else "NULL::integer AS rows"
        return list(conn.execute(
            "SELECT * FROM (SELECT DISTINCT ON (p.dashboard_id, p.chart, p.tags) p.id, p.dashboard_id,"
            f" d.dashboard_title, p.chart, p.tab, p.tags, p.svg, p.comment, p.author_name, p.created_at, {rows}"
            " FROM aisc_report_plot p JOIN dashboards d ON d.id = p.dashboard_id"
            f" WHERE p.dashboard_id IN (SELECT id FROM ({_DASHBOARDS}) pd)"
            " ORDER BY p.dashboard_id, p.chart, p.tags, p.created_at DESC, p.id DESC) newest"
            " ORDER BY dashboard_title, created_at, id", params).fetchall())


def comments(project_id, system_id, *, sources, chart_id) -> list[dict]:
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT c.id, c.parent_id, c.author_name, c.body, c.created_at AT TIME ZONE 'UTC' AS created_at"
                   " FROM aisc_comment c WHERE c.chart_id = %(c)s AND c.deleted_at IS NULL"
                   f" AND c.dashboard_id IN (SELECT id::text FROM ({_DASHBOARDS}) pd"
                   f"                        UNION SELECT slug FROM ({_DASHBOARDS}) ps WHERE slug IS NOT NULL)"
                   " ORDER BY c.created_at, c.id", {"role": _role(project_id), "c": int(chart_id)})
