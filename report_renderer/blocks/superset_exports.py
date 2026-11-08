"""Exported results: one section of the report per tool (a block of the results dashboard with saved plots), titled
with its name; in it, one saved plot after another.

Each plot: its filters as text tags, the vector file saved from Superset with Save to report (shown as it was saved;
nothing is drawn here), the number of rows its chart drew then ("N rows", when the plot was saved with one), who saved
it and when, and the comment. Each tool's commentary is the text written for it in the report's layout (option
`comments`, keyed by the tool's dashboard id), printed where a section prints its commentary. With nothing saved the
block is one section saying how to save."""
from __future__ import annotations

import base64

from markupsafe import Markup
from aisc_report_plugin_interface import BaseBlockRenderer

from ..svg_print import for_print
from ._common import SectionsResult, empty_result, ymd


class SupersetExportsBlock(BaseBlockRenderer):
    type_id = "superset_exports"
    title = "Exported results"
    contract_version = 1
    description = "What was saved from the results dashboard with Save to report: one section per tool."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dashboards": {
                "title": "Tools",
                "description": "Which tools of the results dashboard to show, each as a section of its own.",
                "x-aisc-reference": True,
                # each chosen value prints as a numbered section of its own: the composer numbers them in its
                # outline and draws every choice as a checkbox, all checked for "all"
                "x-aisc-section-per-choice": True,
                "oneOf": [{"const": "all"},
                          {"type": "array", "items": {"type": "string", "minLength": 1, "x-aisc-prose": False}}],
            },
            "comments": {
                "title": "Commentary per tool",
                "description": "Your own words about a tool, printed with its section as a section's commentary.",
                "type": "object",
                "propertyNames": {"minLength": 1},
                "additionalProperties": {"type": "string", "maxLength": 10000, "x-aisc-prose": True},
                # the composer draws one text box per choice of `dashboards`, keyed by its value
                "x-aisc-per-choice-of": "dashboards",
            },
        },
    }
    default_options = {"dashboards": "all", "comments": {}}
    reads = ("superset",)
    choice_options = ("dashboards",)

    def load(self, ctx, options):
        return {"exports": ctx.data.superset_db.exports()}

    def render(self, data, options, ctx):
        t = ctx.t
        wanted = options["dashboards"]
        rows = [r for r in data["exports"] if wanted == "all" or str(r["dashboard_id"]) in set(wanted)]
        if not rows:
            return empty_result(t("Nothing saved yet: in the results dashboard, press Save to report on a block."))
        comments = options.get("comments") or {}
        blocks: dict = {}
        for r in rows:
            blocks.setdefault(r["dashboard_id"], {
                "title": r["dashboard_title"], "plots": [],
                "commentary": comments.get(str(r["dashboard_id"]))})["plots"].append(
                {"chart": r["chart"], "tags": list(r["tags"] or []), "comment": r["comment"], "author": r["author_name"],
                 "date": ymd(r["created_at"]),
                 "rows": t("{count} rows", count=r["rows"]) if r.get("rows") is not None else None,
                 "image": "data:image/svg+xml;base64," + base64.b64encode(
                     for_print(bytes(r["svg"]).decode("utf-8")).encode("utf-8")).decode("ascii")})
        parts = [{"title": b["title"], "commentary": b["commentary"] if isinstance(b["commentary"], str) else None,
                  "html": Markup(self.render_package_template("templates/superset_exports.html.j2", block=b,
                                                              note=n == 0, t=t))}
                 for n, b in enumerate(blocks.values())]
        return SectionsResult(html="".join(str(p["html"]) for p in parts), status="ok", parts=parts)

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "dashboards":
            return [{"value": str(d["id"]), "label": d["dashboard_title"]} for d in ctx.data.superset_db.export_blocks()]
        return []
