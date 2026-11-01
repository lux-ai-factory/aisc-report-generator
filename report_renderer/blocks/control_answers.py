"""The Checklist answers block."""
from __future__ import annotations

from aisc_report_plugin_interface import BaseBlockRenderer

from datetime import timezone

from ..views import load_answers
from ._common import empty_result, finish

#: at most this many answer rows in one Checklist answers block
MAX_ROWS = 1000


def file_size(size: int) -> str:
    """A size as people read it: 512 B, 3.4 KB, 12 MB (as the controls app shows it)."""
    if size < 1024:
        return f"{size} B"
    value, unit = size / 1024, "KB"
    for bigger in ("MB", "GB"):
        if value < 1024:
            break
        value, unit = value / 1024, bigger
    return f"{value:.1f} {unit}" if value < 10 else f"{round(value)} {unit}"


def _when(value) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M")


def proof_files(files: list[dict]) -> list[dict]:
    """A question's proof files as the report lists them: name, type, size, who, when and SHA-256."""
    return [{"name": f["name"], "mime": f["mime"], "size": file_size(f["size"]), "uploaded_by": f["uploaded_by"],
             "when": _when(f["uploaded_at"]), "sha256": f["sha256"]} for f in files]


class ControlAnswersBlock(BaseBlockRenderer):
    type_id = "control_answers"
    title = "Checklist answers"
    contract_version = 1
    description = "The answers given to the project's checklists for this version, with the files that prove them."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "checklists": {
                "title": "Checklists",
                "description": "Which checklists to show.",
                "x-aisc-reference": True,
                "oneOf": [{"const": "all"}, {"type": "array", "items": {"type": "string"}}],
            },
            "show_unanswered": {"type": "boolean", "title": "Show unanswered questions",
                                "description": "Also lists the questions without an answer."},
            "show_scores": {"type": "boolean", "title": "Show scores",
                            "description": "Shows each answer's score and the mean score."},
            "include_archived": {"type": "boolean", "title": "Include archived submissions",
                                 "description": "Also reads submissions that were archived.", "x-aisc-more": True},
        },
    }
    default_options = {"checklists": "all", "show_unanswered": True, "show_scores": True, "include_archived": False}
    reads = ("platform", "controls")
    choice_options = ("checklists",)

    def load(self, ctx, options):
        view = load_answers(ctx, checklists=options["checklists"], include_archived=options["include_archived"])
        newest = None
        if not view.missing_db:
            newest = ctx.data.controls.newest_newer_answer(newer=ctx.data.newer)
        return {"view": view, "newest_newer": newest}

    def render(self, data, options, ctx):
        view = data["view"]
        t = ctx.t
        notices: list[str] = []
        if view.unknown_checklists:
            notices.append(t("{count} selected checklists are not in this project and are not shown.",
                             count=len(view.unknown_checklists)))
        if view.missing_db or not view.checklists:
            r = empty_result(t("No control answers for version {number}.", number=ctx.system["number"]))
            r.notices.extend(notices)
            return r
        budget = MAX_ROWS
        hidden = 0
        lists = []
        for ca in view.checklists:
            rows = [{**r, "files": proof_files(r.get("files") or [])} for r in ca.rows
                    if r["answered"] or options["show_unanswered"]]
            kept = rows[:budget]
            hidden += len(rows) - len(kept)
            budget -= len(kept)
            lists.append({"c": ca, "rows": kept})
        others = sum(ca.other_version_answers for ca in view.checklists)
        if others:
            notices.append(t("{count} answers were given for other versions and are not shown.", count=others))
        html = self.render_package_template("templates/control_answers.html.j2", lists=lists,
                                            show_scores=options["show_scores"], hidden=hidden, t=t,
                                            number=ctx.number)
        return finish(html, notices, newest_newer=data["newest_newer"], t=t)

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "checklists":
            return ctx.data.controls.checklist_choices()
        return []
