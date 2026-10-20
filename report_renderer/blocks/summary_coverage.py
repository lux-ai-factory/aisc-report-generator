"""The Summary and coverage block.

Its own `links` win when non-empty (older layouts keep their links there); otherwise it reads the
layout's coverage map. It can be limited to requirement groups; the counts cover the shown objectives.
"""
from __future__ import annotations

import copy

from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult

from ..coverage import STATUSES, coverage_for
from ..objective_filters import REQUIREMENTS_PROPERTY, Filters, requirement_groups
from ._common import empty_result


class SummaryCoverageBlock(BaseBlockRenderer):
    type_id = "summary_coverage"
    title = "Summary and coverage"
    contract_version = 2
    description = "One table of the objectives and the tests and checklists that cover them."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "show_uncovered_only": {"type": "boolean", "title": "Only objectives without evidence",
                                    "description": "Lists only the objectives that are not covered or have no evidence."},
            "requirements": copy.deepcopy(REQUIREMENTS_PROPERTY),
            "links": {
                "type": "array",
                "maxItems": 200,
                "title": "Own links (before the coverage map)",
                "description": "Links set on this block before the layout's coverage map existed.",
                "x-aisc-reference": True,
                "x-aisc-more": True,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["objective_id"],
                    "properties": {
                        "objective_id": {"type": "string", "minLength": 1},
                        "tests": {"type": "array", "items": {"type": "string"}},
                        "checklists": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }
    default_options = {"links": [], "show_uncovered_only": False, "requirements": "all"}
    reads = ("platform", "control_objectives", "engine", "controls")
    choice_options = ("links.objective_id", "links.tests", "links.checklists", "requirements")

    def load(self, ctx, options):
        co = ctx.data.control_objectives
        if co.assessment() is None:
            return {"assessment": False}
        ids = co.objective_ids()
        links = options["links"] or ctx.report.coverage_links
        return {"assessment": True, "ids": ids, "coverage": coverage_for(ctx, ids, links)}

    def render(self, data, options, ctx):
        t = ctx.t
        if not data["assessment"]:
            return empty_result(t("No control objectives for version {number}.", number=ctx.system["number"]))
        filters = Filters.from_options({"requirements": options.get("requirements", "all")})
        labels = ctx.data.objectives
        coverage = data["coverage"]
        counts = {st: 0 for st in STATUSES}
        rows = []
        for oid in data["ids"]:
            if not filters.objective_shown(oid, labels.get(oid, {}), ()):
                continue
            cov = coverage[oid]
            counts[cov.status] += 1
            if options["show_uncovered_only"] and cov.status not in ("not covered", "no evidence"):
                continue
            rows.append({"id": oid, "label": labels.get(oid, {}).get("label", ""),
                         "tests": [x[0] for x in cov.tests],
                         "checklists": [f"{c[1]} ({c[0]})" for c in cov.checklists], "status": cov.status})
        html = self.render_package_template("templates/summary_coverage.html.j2", rows=rows,
                                            counts=[(st, counts[st]) for st in STATUSES], t=t)
        notices = [filters.notice(t)] if filters.active else []
        return BlockResult(html=html, status="ok", notices=notices)

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "links.objective_id":
            labels = ctx.data.objectives
            return [{"value": oid, "label": f"{oid} {labels.get(oid, {}).get('label', '')}".strip()}
                    for oid in ctx.data.control_objectives.objective_ids()]
        if option_name == "links.tests":
            return ctx.data.engine.tool_choices()
        if option_name == "links.checklists":
            return ctx.data.controls.checklist_choices()
        if option_name == "requirements":
            return [{"value": g, "label": g} for g in requirement_groups(ctx.data.objectives)]
        return []
