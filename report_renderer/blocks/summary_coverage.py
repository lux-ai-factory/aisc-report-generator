"""The Summary and coverage block.

Its own `links` win when non-empty (older layouts keep their links there); otherwise it reads the
layout's coverage map (the snapshot's `coverage_links`, the Evidence map of the version). It can be
limited to requirement groups. The table shows each objective's label and description, its linked tests and
checklists by their labels, and its coverage for the pinned version (coverage.py). Under the table, who
reviewed the version's Evidence map and when (evidence.review), or that it is not reviewed; with the block's
own links, which are not the map, no review is named.
"""
from __future__ import annotations

import copy
from datetime import timezone

from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult

from ..coverage import coverage_for, tool_label
from ..objective_filters import REQUIREMENTS_PROPERTY, Filters, requirement_groups
from ._common import empty_result, ymd


class SummaryCoverageBlock(BaseBlockRenderer):
    type_id = "summary_coverage"
    title = "Summary and coverage"
    contract_version = 2
    description = ("One table of the objectives with their linked tests and checklists and their coverage,"
                   " and who reviewed the evidence map.")
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
        own = bool(options["links"])
        links = options["links"] or ctx.report.coverage_links
        return {"assessment": True, "ids": ids, "coverage": coverage_for(ctx, ids, links),
                "plugins": ctx.data.engine.plugins(), "own_links": own,
                "review": None if own else ctx.data.evidence.review()}

    def render(self, data, options, ctx):
        t = ctx.t
        if not data["assessment"]:
            return empty_result(t("No control objectives for version {number}.", number=ctx.system["number"]))
        filters = Filters.from_options({"requirements": options.get("requirements", "all")})
        labels = ctx.data.objectives
        coverage = data["coverage"]
        rows = []
        for oid in data["ids"]:
            if not filters.objective_shown(oid, labels.get(oid, {}), ()):
                continue
            cov = coverage[oid]
            if options["show_uncovered_only"] and cov.status not in ("not covered", "no evidence"):
                continue
            rows.append({"id": oid, "label": labels.get(oid, {}).get("label", ""),
                         "description": labels.get(oid, {}).get("objective", ""),
                         "tests": [tool_label(name, data["plugins"]) for name, _ in cov.tests],
                         "checklists": [title for _, title, _, _ in cov.checklists], "status": cov.status})
        html = self.render_package_template("templates/summary_coverage.html.j2", rows=rows, t=t,
                                            review=self._review_line(data, ctx))
        notices = [filters.notice(t)] if filters.active else []
        return BlockResult(html=html, status="ok", notices=notices)

    @staticmethod
    def _review_line(data, ctx):
        """(state, text) of the line under the table; None for the block's own links."""
        if data["own_links"]:
            return None
        review = data["review"]
        if review is None:
            return ("not reviewed", ctx.t("The evidence map of version {number} is not reviewed.",
                                          number=ctx.system["number"]))
        return ("reviewed", ctx.t("Evidence map reviewed by {name} on {date}.", name=review["reviewed_by_name"],
                                  date=ymd(review["reviewed_at"].astimezone(timezone.utc))))

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
