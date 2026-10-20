"""The Checklist answers block."""
from __future__ import annotations

from aisc_report_plugin_interface import BaseBlockRenderer

from ..views import load_answers
from ._common import empty_result, finish

#: at most this many answer rows in one Checklist answers block
MAX_ROWS = 1000


class ControlAnswersBlock(BaseBlockRenderer):
    type_id = "control_answers"
    title = "Checklist answers"
    contract_version = 1
    description = "The answers given to the project's checklists for this version."
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
            rows = [r for r in ca.rows if r["answered"] or options["show_unanswered"]]
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
