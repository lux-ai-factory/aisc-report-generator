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
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT DISTINCT s.id, s.slice_name FROM slices s JOIN dashboard_slices ds ON ds.slice_id = s.id"
                   f" WHERE ds.dashboard_id IN (SELECT id FROM ({_DASHBOARDS}) pd) ORDER BY s.slice_name, s.id",
                   {"role": _role(project_id)})


def chart(project_id, system_id, *, sources, chart_id) -> dict | None:
    return db.one(sources.superset_dsn, "superset",
                  "SELECT s.id, s.slice_name, s.viz_type, min(ds.dashboard_id) AS dashboard_id"
                  " FROM slices s JOIN dashboard_slices ds ON ds.slice_id = s.id"
                  f" WHERE s.id = %(c)s AND ds.dashboard_id IN (SELECT id FROM ({_DASHBOARDS}) pd)"
                  " GROUP BY s.id, s.slice_name, s.viz_type", {"role": _role(project_id), "c": int(chart_id)})


def comments(project_id, system_id, *, sources, chart_id) -> list[dict]:
    return db.rows(sources.superset_dsn, "superset",
                   "SELECT c.id, c.parent_id, c.author_name, c.body, c.created_at AT TIME ZONE 'UTC' AS created_at"
                   " FROM aisc_comment c WHERE c.chart_id = %(c)s AND c.deleted_at IS NULL"
                   f" AND c.dashboard_id IN (SELECT id::text FROM ({_DASHBOARDS}) pd"
                   f"                        UNION SELECT slug FROM ({_DASHBOARDS}) ps WHERE slug IS NOT NULL)"
                   " ORDER BY c.created_at, c.id", {"role": _role(project_id), "c": int(chart_id)})
