"""Exported results: one subsection per Superset block; in it, one saved plot after another.

Each plot: its filters as text tags, the vector file saved from Superset with Save to report (shown as it was saved;
nothing is drawn here), who saved it and when, and the comment."""
from __future__ import annotations

import base64

from aisc_report_plugin_interface import BaseBlockRenderer

from ..svg_print import for_print
from ._common import empty_result, finish, ymd


class SupersetExportsBlock(BaseBlockRenderer):
    type_id = "superset_exports"
    title = "Exported results"
    contract_version = 1
    description = "What was saved from the results dashboard with Save to report: one subsection per block."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dashboards": {
                "title": "Blocks",
                "description": "Which blocks of the results dashboard to show.",
                "x-aisc-reference": True,
                "oneOf": [{"const": "all"},
                          {"type": "array", "items": {"type": "string", "minLength": 1, "x-aisc-prose": False}}],
            },
        },
    }
    default_options = {"dashboards": "all"}
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
        blocks: dict = {}
        for r in rows:
            blocks.setdefault(r["dashboard_id"], {"title": r["dashboard_title"], "plots": []})["plots"].append(
                {"chart": r["chart"], "tags": list(r["tags"] or []), "comment": r["comment"], "author": r["author_name"],
                 "date": ymd(r["created_at"]),
                 "image": "data:image/svg+xml;base64," + base64.b64encode(
                     for_print(bytes(r["svg"]).decode("utf-8")).encode("utf-8")).decode("ascii")})
        html = self.render_package_template("templates/superset_exports.html.j2", blocks=blocks, t=t)
        return finish(html, [], newest_newer=None, t=t)

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "dashboards":
            return [{"value": str(d["id"]), "label": d["dashboard_title"]} for d in ctx.data.superset_db.export_blocks()]
        return []
