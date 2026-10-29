"""The Control objectives block.

It can be limited to requirement groups, objectives and a minimum risk impact (by default it shows
everything). The coverage status reads the layout's coverage map (ctx.report.coverage_links). The
priority objectives step 2 stores are marked with their priority score: the sum of the ratings of the
rated risks linked to them, as step 2 computes it.
"""
from __future__ import annotations

import copy

from aisc_report_plugin_interface import BaseBlockRenderer

from ..coverage import coverage_for
from ..objective_filters import REQUIREMENTS_PROPERTY, Filters, requirement_groups
from ._common import empty_result, finish


def _priority_scores(rows, priority_ids) -> dict[str, int]:
    """{priority objective: the sum of the ratings of the rated risks linked to it}."""
    scores = {}
    for oid in priority_ids:
        ratings = {r["risk_id"]: r["rating"] for r in rows if r["objective_id"] == oid}
        scores[oid] = sum(v for v in ratings.values() if v is not None)
    return scores


class ControlObjectivesBlock(BaseBlockRenderer):
    type_id = "control_objectives"
    title = "Control objectives"
    contract_version = 2
    description = "The control objectives mapped to the version's risks, with their coverage."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "group_by": {"enum": ["objective", "risk"], "title": "Group by",
                         "description": "List the objectives, or the risks with their objectives.",
                         "x-aisc-enum-labels": {"objective": "Objective", "risk": "Risk"}},
            "requirements": copy.deepcopy(REQUIREMENTS_PROPERTY),
            "min_severity": {"type": ["integer", "null"], "minimum": 1, "maximum": 5,
                             "title": "Minimum risk impact",
                             "description": "Show only objectives with a risk of at least this impact (1 to 5).",
                             "x-aisc-null-label": "All risks"},
            "show_status": {"type": "boolean", "title": "Show coverage",
                            "description": "Shows each objective's coverage from the layout's coverage map."},
            "show_rationale": {"type": "boolean", "title": "Show rationale",
                               "description": "Shows why each risk was mapped to the objective.", "x-aisc-more": True},
            "show_quotes": {"type": "boolean", "title": "Show quotes",
                            "description": "Shows the quoted source text of each mapping.", "x-aisc-more": True},
            "objectives": {"title": "Objectives", "description": "Show only these objectives.",
                           "x-aisc-reference": True, "x-aisc-more": True,
                           "oneOf": [{"const": "all"}, {"type": "array", "items": {"type": "string", "minLength": 1}}]},
            "include_unrated": {"type": "boolean", "title": "Include unrated risks",
                                "description": "With a minimum impact, risks without an impact still count.",
                                "x-aisc-more": True},
            "show_severity": {"type": "boolean", "title": "Show rating",
                              "description": "Shows each risk's impact, likelihood and rating.", "x-aisc-more": True},
        },
    }
    default_options = {"group_by": "objective", "show_rationale": True, "show_quotes": False, "show_status": True,
                       "requirements": "all", "objectives": "all", "min_severity": None, "include_unrated": True,
                       "show_severity": False}
    reads = ("platform", "control_objectives", "engine", "controls")
    choice_options = ("requirements", "objectives")

    def load(self, ctx, options):
        co = ctx.data.control_objectives
        assessment = co.assessment()
        if assessment is None:
            return {"assessment": None}
        rows = co.mappings()
        ids = co.objective_ids()
        coverage = coverage_for(ctx, ids, ctx.report.coverage_links) if options["show_status"] else {}
        return {"assessment": assessment, "rows": rows, "ids": ids, "run": co.mapping_run(),
                "coverage": coverage, "newest_newer": co.newest_newer_assessment(),
                "priority": _priority_scores(rows, co.priority_ids())}

    def render(self, data, options, ctx):
        t = ctx.t
        if data["assessment"] is None:
            return empty_result(t("No control objectives for version {number}.", number=ctx.system["number"]))
        filters = Filters.from_options(options)
        labels = ctx.data.objectives
        rows = data["rows"]
        priority = {oid: t("Priority objective, score {score}", score=score) for oid, score in data["priority"].items()}
        objectives = []
        shown_ids = set()
        for oid in data["ids"]:
            info = labels.get(oid, {})
            risks = [r for r in rows if r["objective_id"] == oid]
            if not filters.objective_shown(oid, info, risks):
                continue
            shown_ids.add(oid)
            risks = [dict(r, rating_text=self._rating(t, r)) for r in risks]
            cov = data["coverage"].get(oid)
            objectives.append({"id": oid, "info": info, "risks": risks,
                               "status": cov.status if cov else None, "priority": priority.get(oid)})
        risks = []
        for r in rows:
            if not risks or risks[-1]["risk_id"] != r["risk_id"]:
                risks.append({"risk_id": r["risk_id"], "text": r["text"], "impact": r["impact"],
                              "likelihood": r["likelihood"], "rating": r["rating"], "band": r["band"],
                              "objectives": [], "mapped": False})
            if r["objective_id"]:
                risks[-1]["mapped"] = True
                if r["objective_id"] in shown_ids:
                    risks[-1]["objectives"].append({"id": r["objective_id"],
                                                    "label": labels.get(r["objective_id"], {}).get("label", ""),
                                                    "priority": priority.get(r["objective_id"])})
        if filters.active:
            kept = []
            for r in risks:
                if not filters.risk_passes(r):
                    continue
                if r["mapped"] and not r["objectives"]:
                    continue
                if not r["mapped"] and filters.narrows_objectives:
                    continue
                kept.append(r)
            risks = kept
        for r in risks:
            r["rating_text"] = self._rating(t, r)
        notices = []
        run = data["run"]
        if run is not None and run["stop"] != "clean":
            notices.append(t("The mapping run stopped: {stop}.", stop=run["stop"]))
        if filters.active:
            notices.append(filters.notice(t))
        nothing = filters.active and ((options["group_by"] == "risk" and not risks)
                                      or (options["group_by"] != "risk" and not objectives))
        html = self.render_package_template(
            "templates/control_objectives.html.j2", group_by=options["group_by"], objectives=objectives,
            risks=risks, show_rationale=options["show_rationale"], show_quotes=options["show_quotes"],
            show_status=options["show_status"], show_severity=options["show_severity"], nothing=nothing, t=t)
        return finish(html, notices, newest_newer=data["newest_newer"], t=t)

    @staticmethod
    def _rating(t, risk) -> str:
        """e.g. "Impact 5, likelihood 4: rating 20 (Critical)"; "Not rated" until both parts are set."""
        if risk["rating"] is None:
            return t("Not rated")
        return t("Impact {impact}, likelihood {likelihood}: rating {rating} ({band})", impact=risk["impact"],
                 likelihood=risk["likelihood"], rating=risk["rating"], band=t(risk["band"]))

    def choices(self, ctx, option_name) -> list[dict]:
        labels = ctx.data.objectives
        if option_name == "requirements":
            return [{"value": g, "label": g} for g in requirement_groups(labels)]
        if option_name == "objectives":
            return [{"value": oid, "label": f"{oid} {labels.get(oid, {}).get('label', '')}".strip()}
                    for oid in ctx.data.control_objectives.objective_ids()]
        return []
