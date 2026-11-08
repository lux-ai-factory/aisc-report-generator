"""The project's own control answers, in its database project_<hex>.

The database name is built from the project's pid and checked; a project without its own database,
or a database without the controls tables, reads as nothing (None or []), never as an error.
"""
from __future__ import annotations

from . import db
from .scope import check_uuid


def _dsn(project_id, system_id, sources) -> str | None:
    """The project's database (whether it exists is remembered for a moment, see db.project_dsn)."""
    return db.project_dsn(sources, check_uuid(project_id))


def _read(dsn, sql, params=None, *, absent):
    """db.rows on the project's database; `absent` when the controls schema or a table is not there."""
    try:
        return db.rows(dsn, "controls", sql, params)
    except db._ABSENT:
        return absent


def checklists(project_id, system_id, *, sources) -> list[dict] | None:
    dsn = _dsn(project_id, system_id, sources)
    if dsn is None:
        return None
    return _read(dsn,
                 'SELECT c.id, c.title, c."controlTopic" AS control_topic, s.name AS source_name'
                 ' FROM controls.checklist c LEFT JOIN controls.source s ON s.id = c."sourceId"'
                 " ORDER BY c.title, c.id", absent=None)


def submissions_with_answers(project_id, system_id, *, sources, include_archived) -> list[dict] | None:
    dsn = _dsn(project_id, system_id, sources)
    if dsn is None:
        return None
    return _read(dsn,
                 'SELECT sub.id, sub."checklistId" AS checklist_id, sub.label, sub.status::text AS status,'
                 " sub.version, sub.questions_version, sub.created_at, sub.archived_at IS NOT NULL AS archived"
                 " FROM controls.submission sub"
                 " WHERE EXISTS (SELECT 1 FROM controls.submission_answer a"
                 '               WHERE a."submissionId" = sub.id AND a.system_version_pid = %(s)s)'
                 " AND (%(arch)s OR sub.archived_at IS NULL)"
                 ' ORDER BY sub."checklistId", sub.version DESC, sub.created_at DESC, sub.id DESC',
                 {"s": check_uuid(system_id), "arch": bool(include_archived)}, absent=None)


def questions(project_id, system_id, *, sources, checklist_ids) -> list[dict]:
    dsn = _dsn(project_id, system_id, sources)
    if dsn is None or not checklist_ids:
        return []
    return _read(dsn,
                 'SELECT q.id, q."checklistId" AS checklist_id, q."order" AS position, q.text, q.article'
                 ' FROM controls.checklist_question q WHERE q."checklistId" = ANY(%(ids)s::text[])'
                 ' ORDER BY q."checklistId", q."order", q.id', {"ids": list(checklist_ids)}, absent=[])


def answers(project_id, system_id, *, sources, submission_ids) -> list[dict]:
    """With the question each answer keeps (question_text NULL: none, as in a draft); question_id is NULL
    for an answer of a closed submission whose question was removed since."""
    dsn = _dsn(project_id, system_id, sources)
    if dsn is None or not submission_ids:
        return []
    return _read(dsn,
                 'SELECT a.id, a."submissionId" AS submission_id, a."questionId" AS question_id, a.answer, a.score,'
                 " a.system_version_pid::text AS system_version_pid, a.question_text, a.question_article,"
                 " a.question_order FROM controls.submission_answer a"
                 ' WHERE a."submissionId" = ANY(%(ids)s::text[]) ORDER BY a."submissionId", a.id',
                 {"ids": list(submission_ids)}, absent=[])


def answer_files(project_id, system_id, *, sources, answer_ids) -> list[dict]:
    """The proof files linked to these answers, oldest first: what each file is and who attached it when, never
    its bytes. A database made before proof files existed has no such table and reads as none."""
    dsn = _dsn(project_id, system_id, sources)
    if dsn is None or not answer_ids:
        return []
    return _read(dsn,
                 "SELECT f.answer_id, f.name, f.mime, f.size, f.sha256, f.uploaded_by, f.uploaded_at"
                 " FROM controls.submission_answer_file f WHERE f.answer_id = ANY(%(ids)s::text[])"
                 " ORDER BY f.answer_id, f.uploaded_at, f.id", {"ids": list(answer_ids)}, absent=[])


def newest_newer_answer(project_id, system_id, *, sources, newer) -> int | None:
    numbers = {str(n["pid"]): n["number"] for n in newer}
    if not numbers:
        return None
    dsn = _dsn(project_id, system_id, sources)
    if dsn is None:
        return None
    found = _read(dsn,
                  "SELECT DISTINCT system_version_pid::text AS pid FROM controls.submission_answer"
                  " WHERE system_version_pid = ANY(%(pids)s::uuid[])", {"pids": list(numbers)}, absent=[])
    hits = [numbers[r["pid"]] for r in found if r["pid"] in numbers]
    return max(hits) if hits else None


def submission_choices(project_id, system_id, *, sources) -> list[dict]:
    """Every submission with answers for the version, archived ones too, newest first within each checklist:
    "<checklist> · <label> · version <n> · <status>[, archived] · <created>"."""
    titles = {c["id"]: c["title"] for c in checklists(project_id, system_id, sources=sources) or []}
    subs = submissions_with_answers(project_id, system_id, sources=sources, include_archived=True) or []
    subs = sorted(subs, key=lambda s: titles.get(s["checklist_id"], ""))   # stable: keeps newest first within each
    return [{"value": s["id"], "label": " · ".join([
        titles.get(s["checklist_id"], s["checklist_id"]), s["label"], f"version {s['version']}",
        s["status"] + (", archived" if s["archived"] else ""), s["created_at"].strftime("%Y-%m-%d %H:%M")])}
        for s in subs]


def checklist_choices(project_id, system_id, *, sources) -> list[dict]:
    rows = checklists(project_id, system_id, sources=sources)
    return [{"value": r["id"], "label": r["title"]} for r in rows or []]
